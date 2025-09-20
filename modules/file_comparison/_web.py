"""Реализует веб-обработчики, отдающие сведения из БД."""
import dataclasses
import logging

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
import quart

from .models import FileDataRepository


class SubmissionQuery(BaseModel):
    """Параметры запроса о файлах из ответа на задание."""
    minratio: float = Field(default=0.7, ge=0.0, le=1.0, description='Допустимый уровень сходства файлов')
    maxfiles: int = Field(default=5, ge=1, le=10, description='Сколько файлов передавать')
    shownewer: bool = Field(default=False, description='Показывать ли более новые похожие файлы')


@dataclasses.dataclass
class RegistrationContext:
    """Зависимости, требуемые для реализации обработчика."""
    repository: FileDataRepository = None
    log: logging.Logger = None


adapter = TypeAdapter(SubmissionQuery)
context: RegistrationContext = RegistrationContext()
blueprint: quart.Blueprint = quart.Blueprint(
    name='filecomp', import_name='modules.file_comparison',
    url_prefix='/filecomp', template_folder='templates',
    static_folder='static', static_url_path='static')


@blueprint.route('/submission/<int:submission_id>', methods=['GET'])
async def load_submission_info(submission_id: int):
    """Возвращает сведения о файлах из указанного ответа на задание."""
    raw_query = quart.request.args.to_dict()
    try:
        query = adapter.validate_python(raw_query)
    except ValidationError as err:
        err: ValidationError
        err_msgs = [details['msg'] for details in err.errors()]
        return {'files': {}, 'errors': err_msgs}, 422
    info = await context.repository.get_files_by_submission(
        submission_id=submission_id,
        min_score=query.minratio,
        max_similar=query.maxfiles,
        show_newer=query.shownewer
    )
    return {'files': {
        fname: {
            'known': True,
            'older': [
                {
                    'name': f.file_name,
                    'url': f.file_url,
                    'author': f.user_name,
                    'author_id': f.user_id,
                    'similarity': f.similarity_score,
                }
                for f in details.earlier_files
            ],
            'newer': [
                {
                    'name': f.file_name,
                    'url': f.file_url,
                    'author': f.user_name,
                    'author_id': f.user_id,
                    'similarity': f.similarity_score,
                }
                for f in details.later_files
            ],
            'warnings': [
                {'type': w.type, 'message': w.message}
                for w in details.warnings
            ],
        }
        for fname, details in info.items()
    }, 'errors': {}}, 200
