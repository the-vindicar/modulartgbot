"""Реализует логику Telegram-бота для работы с нагрузкой."""
from io import BytesIO
import logging
import datetime
from pathlib import Path

from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BufferedInputFile
from aiogram.filters import Command, or_f
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
import openpyxl

from .parsing import parse_workload, fill_template, TeacherWorkload


__all__ = ['router', 'log']
router = Router(name='workload')
log = logging.getLogger('modules.workload')
template_path = Path(__file__).parent / 'template.xlsx'
cache: dict[int, tuple[str, dict[str, TeacherWorkload]]] = {}


class WorkloadStates(StatesGroup):
    """Состояния при работе с нагрузкой."""
    ExpectingFile = State()
    ExpectingName = State()


@router.message(Command('workload'))
async def workload_cmd(msg: Message, state: FSMContext):
    """Позволяет создать упрощённую выжимку из данных о нагрузке."""
    if not template_path.is_file():
        await msg.answer('Извините, команда недоступна. Сообщите администратору.')
        return
    await state.set_state(WorkloadStates.ExpectingFile)
    await msg.answer('Пожалуйста, отправьте файл с нагрузкой (формат Excel).\r\n'
                     'Для отмены отправьте /no')


@router.message(Command('/no'), or_f(WorkloadStates.ExpectingName, WorkloadStates.ExpectingFile))
async def cancel(msg: Message, state: FSMContext):
    """Отменяет операцию."""
    await state.set_state(None)
    cache.pop(msg.from_user.id, None)
    await msg.reply('Операция завершена.', reply_markup=ReplyKeyboardRemove(selective=True))


@router.message(WorkloadStates.ExpectingFile)
async def receive_document(msg: Message, state: FSMContext):
    """Обрабатывает переданный файл."""
    if not msg.document:
        await msg.answer('Простите, но вы не приложили файл к сообщению.')
        return
    if not msg.document.file_name or not msg.document.file_name.lower().endswith('.xlsx'):
        await msg.answer('Простите, но приложенный файл не является Excel-файлом.')
        return
    try:
        target = BytesIO()
        await msg.bot.download(msg.document.file_id, destination=target)
        target.seek(0)
        wb = openpyxl.load_workbook(target, read_only=False)
        workloads = parse_workload(wb[wb.sheetnames[0]])
        if len(workloads) == 0:
            raise ValueError('No data returned! len(workloads) == 0')
    except Exception as err:
        log.warning('Failed to process workload file! File id: %s', msg.document.file_id, exc_info=err)
        await msg.reply('Простите, но мне не удалось обработать этот файл.\r\n'
                        'Убедитесь, что он корректен, или обратитесь к администратору.\r\n'
                        f'Покажите ему файл и сообщите этот ID: `{msg.document.file_id}`')
    else:
        all_names = sorted(workloads.keys())
        if len(all_names) == 1:
            await msg.answer('В файле данные только для одного предподавателя. Вот они.')
            await handle_name(msg, all_names[0])
        else:
            cache[msg.from_user.id] = msg.document.file_id, workloads
            await state.set_state(WorkloadStates.ExpectingName)
            btns = [KeyboardButton(text=name) for name in all_names]
            N = 3  # сколько кнопок в строке
            rows = [btns[N*i:N*(i+1)] for i in range(len(btns) // N + int(len(btns) % N > 0))]
            markup = ReplyKeyboardMarkup(keyboard=[*rows, [KeyboardButton(text='/no')]],
                                         one_time_keyboard=False, selective=True)
            await msg.reply('Введите фамилию и.о. того преподавателя, для которого вы хотите получить нагрузку.\r\n'
                            'Введите /no, когда закончите.', reply_markup=markup)


@router.message(WorkloadStates.ExpectingName)
async def receive_name(msg: Message, state: FSMContext):
    """Принимает имя преподавателя для извлечения нагрузки."""
    name = msg.text.strip()
    if msg.from_user.id not in cache:
        await state.set_state(None)
        await msg.answer('Что-то пошло не так! Попробуйте начать с начала (с команды /workload ).')
        return
    file_id, workloads = cache[msg.from_user.id]
    if name in workloads:
        await handle_name(msg, name)
    else:
        partial_matches = [wname for wname in workloads.keys() if name.lower() in wname.lower()]
        if len(partial_matches) == 1:
            await handle_name(msg, partial_matches[0])
        else:
            await msg.answer('Извините, но вам нужно указать имя более чётко. Используйте предложенную клавиатуру.')


async def handle_name(msg: Message, name: str) -> None:
    """Обрабатывает имя. Оно уже заведомо корректно."""
    file_id, workloads = cache[msg.from_user.id]
    workload = workloads[name]
    now = datetime.datetime.now()
    year = now.year if 7 <= now.month <= 12 else (now.year - 1)

    try:
        result = fill_template(template_path, year, workload)
        buffer = BytesIO()
        result.save(buffer)
        buffer.seek(0)
        file = BufferedInputFile(buffer.read(), f'{name} ({year}-{year+1}).xlsx')
        await msg.answer_document(file, caption=f'Нагрузка для {name} ({year}-{year+1})')
    except Exception as err:
        log.warning('Failed to respond with workload! File ID: %s', file_id, exc_info=err)
        await msg.answer('Простите, но что-то пошло не так при подготовке данных.\r\n'
                         f'Обратитесь к администратору и сообщите этот ID: `{file_id}`')
