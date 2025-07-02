"""This submodule deals with Moodle private messaging system."""
import typing as t
import enum

from pydantic import BaseModel, Field, PositiveInt, AnyHttpUrl

from .common import *


__all__ = [
    'MessagesMixin',
    'SendMessage', 'SendInstantMessage',
    'MessageType', 'MessageReadStatus', 'ConvType',
    'RMessage'
]


class SendMessage(BaseModel):
    """Message we are trying to send."""
    text: str
    textformat: FormatEnum = FormatEnum.FORMAT_MOODLE


class RConvMessage(BaseModel):
    """A message that already exists in a conversation."""
    id: PositiveInt
    useridfrom: PositiveInt
    text: str
    timecreated: Timestamp


class ConvType(enum.IntEnum):
    """Types of conversations."""
    INDIVIDUAL = 1
    GROUP = 2
    SELF = 3


class RConvListing(BaseModel):
    """A short description of a conversation."""
    id: PositiveInt
    type: ConvType
    name: str = ''
    timecreated: Timestamp


class ContactRequest(BaseModel):
    """A contact request from a user."""
    id: PositiveInt
    userid: PositiveInt
    requesteduserid: PositiveInt
    timecreated: Timestamp


class RConvMember(BaseModel):
    """Conversation member."""
    id: PositiveInt
    fullname: str
    profileurl: AnyHttpUrl
    profileimageurl: AnyHttpUrl
    profileimageurlsmall: AnyHttpUrl
    isonline: bool
    showonlinestatus: bool
    isblocked: bool
    iscontact: bool
    isdeleted: bool
    canmessageevenifblocked: bool
    canmessage: bool
    requirescontact: bool
    cancreatecontact: bool
    contactrequests: list[ContactRequest] = Field(default_factory=list)
    conversations: list[RConvListing] = Field(default_factory=list)


class RConversation(BaseModel):
    """A conversation with another user."""
    id: PositiveInt
    type: ConvType
    membercount: int
    ismuted: bool
    isfavourite: bool
    isread: bool
    unreadcount: t.Optional[int] = None
    name: t.Optional[str] = None
    subname: t.Optional[str] = None
    imageurl: t.Optional[AnyHttpUrl] = None
    candeletemessagesforallusers: bool = False
    members: list[RConvMember] = Field(default_factory=list)
    messages: list[RConvMessage] = Field(default_factory=list)


class RConvList(BaseModel):
    conversations: list[RConversation]


class SendInstantMessage(BaseModel):
    """A description of an instant message we want to send."""
    touserid: PositiveInt
    text: str
    textformat: FormatEnum = FormatEnum.FORMAT_MOODLE
    clientmsgid: t.Optional[str] = Field(default=None, pattern=r'^[0-9a-zA-Z]*$')


class RInstantMessageReport(BaseModel):
    """Reports success or failure of sending an instant message."""
    msgid: int
    text: str = ''
    timecreated: Timestamp = 0
    conversationid: int = 0
    useridfrom: int = 0
    candeletemessagesforallusers: bool = False
    clientmsgid: str = None
    errormessage: t.Optional[str] = None

    @property
    def failed(self) -> bool:
        """True if message hasn't been sent."""
        return self.msgid == -1


class MessageType(enum.StrEnum):
    """Types of messages to receive."""
    BOTH = 'both'
    NOTIFICATIONS = 'notifications'
    CONVERSATIONS = 'conversations'


class MessageReadStatus(enum.IntEnum):
    """Read or unread status of messages to receive."""
    UNREAD = 0
    READ = 1
    ALL = 2


class RMessage(BaseModel):
    id: PositiveInt
    useridfrom: int
    userfromfullname: str
    useridto: int
    usertofullname: str
    subject: str
    text: str
    fullmessage: str
    fullmessageformat: FormatEnum
    fullmessagehtml: str
    smallmessage: str
    notification: bool
    timecreated: Timestamp
    timeread: t.Optional[Timestamp] = None
    contexturl: t.Optional[str] = None
    contenxturllinkname: t.Optional[str] = None
    component: t.Optional[str] = None
    eventtype: t.Optional[str] = None
    customdata: t.Optional[str] = None
    iconurl: t.Optional[str] = None


class RMessages(BaseModel):
    messages: list[RMessage] = Field(default_factory=list)
    warnings: list[RWarning] = Field(default_factory=list)


class RConvMessages(BaseModel):
    id: PositiveInt
    members: list[RConvMember] = Field(default_factory=list)
    messages: list[RConvMessage] = Field(default_factory=list)


class RMarkAsReadMessage(BaseModel):
    messageid: PositiveInt
    warnings: list[RWarning] = Field(default_factory=list)


class RMarkAsReadNotification(BaseModel):
    notificationid: PositiveInt
    warnings: list[RWarning] = Field(default_factory=list)


class MessagesMixin:
    """Mixin providing methods for working with private messages."""
    # region Conversation API
    async def core_message_get_conversations(
            self: WebServiceAdapter,
            userid: int,
            limitfrom: int = 0,
            limitnum: int = 0,
            type: t.Optional[ConvType] = None,
            favourites: t.Optional[bool] = None,
            mergeself: bool = False
    ) -> RConvList:
        """Retrieves the list of conversations owned by the specific user.

        :param userid: ID of the user who owns those conversations.
            Typically, this will be our own user ID, as given in ``Moodle.me.id``.
        :param limitfrom: Pagination. Number of conversations to skip.
        :param limitnum: Pagination. Number of conversations to retrieve after skipping.
        :param type: Conversation type. If None, return conversations of any type.
        :param favourites: True - only get favourite conversations. False - only get non-favourite. None - get all.
        :param mergeself: If True and private conversations are requested, include the self-conversation as well.
        :returns: List of matching conversations.
        """
        return await self('core_message_get_conversations', dict(
            userid=userid, limitfrom=limitfrom, limitnum=limitnum,
            type=type, favourites=favourites, mergeself=mergeself
        ), model=RConvList)

    async def core_message_send_messages_to_conversation(
            self: WebServiceAdapter, conversationid: int, *messages: t.Union[SendMessage, str]
    ) -> list[RConvMessage]:
        """Sends one or more messages to the specified conversation.

        :param conversationid: ID of the conversation to send the messages to.
        :param messages: Sequence of messages to send, either strings or messages with specific formatting.
        :returns: List of message objects corresponding to the sent messages.
        """
        return await self('core_message_send_messages_to_conversation', dict(
            conversationid=conversationid, messages=messages
        ), model=list[RConvMessage])

    async def core_message_get_conversation_messages(
            self: WebServiceAdapter, currentuserid: int, convid: int,
            limitfrom: int = 0, limitnum: int = 0, newest: bool = False, timefrom: int = 0
    ) -> RConvMessages:
        """Retrieves messages from the given conversation.

        :param currentuserid: ID of the current user. See ``Moodle.me.id``.
        :param convid: ID of the conversation.
        :param limitfrom: Pagination. Number of messages to skip.
        :param limitnum: Pagination. Number of messages to retrieve after skipping.
        :param newest: If True, return newest messages first.
        :param timefrom: If not 0, only return messages sent later than this timestamp.
        :return:
        """
        return await self('core_message_get_messages', dict(
            currentuserid=currentuserid, convid=convid, timefrom=timefrom,
            newest=newest, limitfrom=limitfrom, limitnum=limitnum
        ), model=RConvMessages)

    async def core_message_get_unread_conversations_count(
            self: WebServiceAdapter, useridto: t.Union[int, t.Literal[0]]
    ) -> int:
        """How many conversations have unread messages?

        :param useridto: Recipient of the messages. Usually our own ID. See ``Moodle.me.id``.
        :returns: Amount of conversations with unread messages."""
        return await self('core_message_get_unread_conversations_count', dict(useridto=useridto), model=int)
    # endregion

    async def core_message_mark_message_read(
            self: WebServiceAdapter, messageid: int, timeread: int = 0
    ) -> RMarkAsReadMessage:
        """Marks a single message as having been read.

        :param messageid: ID of the message to mark as read.
        :param timeread: Timestamp to mark the message with. 0 means server current time.
        :return:
        """
        return await self('core_message_mark_message_read', dict(
            messageid=messageid, timeread=timeread
        ), model=RMarkAsReadMessage)

    async def core_message_mark_notification_read(
            self: WebServiceAdapter, notificationid: int, timeread: int = 0
    ) -> RMarkAsReadNotification:
        """Marks a single notification as having been read.

        :param notificationid: ID of the message to mark as read.
        :param timeread: Timestamp to mark the message with. 0 means server current time.
        :return:
        """
        return await self('core_message_mark_notification_read', dict(
            notificationid=notificationid, timeread=timeread
        ), model=RMarkAsReadNotification)

    async def core_message_mark_all_conversation_messages_as_read(
            self: WebServiceAdapter, userid: int, conversationid: int
    ) -> None:
        """Marks all messages in a conversation as having been read.

        :param userid: ID of the user who marks the conversation. Usually our own ID. See ``Moodle.me.id``.
        :param conversationid: Which conversation to mark as read.
        :return:
        """
        return await self('core_message_mark_all_conversation_messages_as_read', dict(
            userid=userid, conversationid=conversationid
        ), model=None)

    async def core_message_send_instant_messages(
            self: WebServiceAdapter, *messages: SendInstantMessage
    ) -> list[RInstantMessageReport]:
        """Send a set of instant messages.

        :param messages: Texts and targets for the messages.
        :returns: Success or failure reports. User clientmsgid field to figure out which report is for which message.
        """
        return await self('core_message_send_instant_messages', dict(messages=messages),
                          model=list[RInstantMessageReport])

    async def core_message_get_messages(
            self: WebServiceAdapter,
            useridto: t.Union[int, t.Literal[0]],
            useridfrom: t.Union[int, t.Literal[0, -10, -20]] = 0,
            type: MessageType = MessageType.BOTH,
            read: MessageReadStatus = MessageReadStatus.READ,
            newestfirst: bool = True,
            limitfrom: int = 0,
            limitnum: int = 0
    ) -> RMessages:
        """Retrieves messages.

        :param useridto: Recipient of the message. 0 for any (useful for retrieving outgoing messages).
        :param useridfrom: Sender of the message. 0 for any, -10 for no-reply system user, -20 for support system user.
        :param type: Message type: conversations or notifications. Or both.
        :param read: Read status of the message. Useful for getting unread messages only.
        :param newestfirst: How to sort the messages in the result.
        :param limitfrom: Pagination. Number of messages to skip.
        :param limitnum: Pagination. Number of messages to retrieve after skipping.
        """
        return await self('core_message_get_messages', dict(
            useridfrom=useridfrom, useridto=useridto, type=type, read=read,
            newestfirst=newestfirst, limitfrom=limitfrom, limitnum=limitnum
        ), model=RMessages)
