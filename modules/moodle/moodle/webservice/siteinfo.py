from typing import Optional, Any
from pydantic import BaseModel, PositiveInt, AnyHttpUrl, Field
from .common import *


__all__ = ['RSiteInfo', 'RAdvancedFeature', 'RAvailableFunction', 'SiteInfoMixin']


class RAdvancedFeature(BaseModel):
    name: str
    value: Any


class RAvailableFunction(BaseModel):
    name: str
    version: str


class RSiteInfo(BaseModel):
    sitename: str
    username: str
    firstname: str
    lastname: str
    fullname: str
    lang: str
    userid: PositiveInt
    siteurl: AnyHttpUrl
    userpictureurl: str
    functions: list[RAvailableFunction] = Field(default_factory=list)
    downloadfiles: Optional[bool] = None
    uploadfiles: Optional[bool] = None
    release: Optional[str] = None
    version: Optional[str] = None
    mobilecssurl: Optional[str] = None
    advancedfeatures: list[RAdvancedFeature] = Field(default_factory=list)
    usercanmanageownfiles: Optional[bool] = None
    userquota: Optional[int] = None
    usermaxuploadfilesize: Optional[int] = None
    userhomepage: Optional[int] = None
    userhomepageurl: Optional[str] = None
    userprivateaccesskey: Optional[str] = None
    siteid: Optional[int] = None
    sitecalendartype: Optional[str] = None
    usercalendartype: Optional[str] = None
    userissiteadmin: Optional[bool] = None
    theme: Optional[Any] = None
    limitconcurrentlogins: Optional[int] = None
    usersessionscount: Optional[int] = None
    policyagreed: Optional[int] = None


class SiteInfoMixin:
    async def core_webservice_get_site_info(self: WebServiceAdapter) -> RSiteInfo:
        return await self('core_webservice_get_site_info', {}, model=RSiteInfo)
