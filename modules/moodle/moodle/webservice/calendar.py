"""This submodule works with calendar component."""
from typing import Optional, Any, Collection, Union
from datetime import datetime

from pydantic import BaseModel, PositiveInt, Field

from .common import *


__all__ = [
    'CalendarMixin',
    'RCalendarEvent', 'RCalendarEvents',
    'RUpdateEventDay',
    'CalendarEvent', 'DeleteEvent',
]


class CalendarEvent(BaseModel):
    """Describes a calendar event we wish to create."""
    name: str
    description: str = None
    format: FormatEnum = FormatEnum.FORMAT_HTML
    timestart: Timestamp
    timeduration: int = 0
    visible: bool = True
    eventtype: str = 'user'
    sequence: int = 1
    repeats: int = 0
    courseid: int = 0
    groupid: int = 0


class DeleteEvent(BaseModel):
    """Describes a set of calendar events that should be deleted."""
    eventid: PositiveInt
    repeat: bool


class RCalendarEvent(BaseModel):
    """Describes a calendar event returned by the server."""
    id: PositiveInt
    name: str
    courseid: PositiveInt
    groupid: PositiveInt
    userid: PositiveInt
    repeatid: PositiveInt
    instance: PositiveInt
    eventtype: str
    timestart: Timestamp
    timeduration: int
    visible: bool
    sequence: int
    timemodified: Timestamp
    subscriptionid: Optional[int] = None
    uuid: Optional[str] = None
    modulename: Optional[str] = None
    categoryid: Optional[int] = None
    description: Optional[str] = None
    format: Optional[FormatEnum] = None


class RCalendarEvents(BaseModel):
    """Describes a list of calendar events."""
    events: list[RCalendarEvent]
    warnings: list[RWarning]


class RUpdateEventDay(BaseModel):
    """Describes a result of updating event's day. Sadly, documentation is hard ot read on this one."""
    event: Any


class CalendarMixin(WebServiceFunctions):
    """Mixin providing methods for working with Moodle calendar."""
    async def get_calendar_events(
            self,
            timestart: Union[datetime, int] = 0,
            timeend: Union[datetime, int] = 0,
            *,
            current_user_events: bool = True,
            site_events: bool = True,
            ignore_hidden: bool = True,
            eventids: Collection[int] = (),
            courseids: Collection[int] = (),
            groupids: Collection[int] = (),
            categoryids: Collection[int] = (),
    ) -> RCalendarEvents:
        """Retrieves the list of calendar events matching the given parameters."""
        return await self._owner('core_calendar_get_calendar_events', dict(
            events=dict(eventids=eventids, courseids=courseids, groupids=groupids, categoryids=categoryids),
            options=dict(userevents=current_user_events, siteevents=site_events, ignorehidden=ignore_hidden,
                         timestart=timestart, timeend=timeend)
        ), model=RCalendarEvents)

    async def create_calendar_events(
            self,
            events: Collection[CalendarEvent]
    ) -> RCalendarEvents:
        """Creates one or more calendar events."""
        return await self._owner('core_calendar_create_calendar_events', dict(
            events=events
        ), model=RCalendarEvents)

    async def delete_calendar_events(
            self,
            events: Collection[DeleteEvent]
    ) -> None:
        """Deletes one or more events from the calendar."""
        return await self._owner('core_calendar_delete_calendar_events', dict(events=events), model=None)

    async def update_event_start_day(self, eventid: PositiveInt, daytimestamp: Timestamp) -> RUpdateEventDay:
        """Changes the day for the given event, without changing anything else.
        Only day portion is extracted from daytimestamp, and time portion is ignored."""
        return await self._owner('core_calendar_update_event_start_day', dict(
            eventid=eventid, daytimestamp=daytimestamp
        ), model=RUpdateEventDay)
