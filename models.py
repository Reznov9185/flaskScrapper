import datetime
from sqlalchemy import Column, Integer, String, ARRAY, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.inspection import inspect

class Serializer(object):

    def serialize(self):
        return {c: getattr(self, c) for c in inspect(self).attrs.keys()}

    @staticmethod
    def serialize_list(l):
        return [m.serialize() for m in l]

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True)
    email = Column(String(120), unique=True)

    def __init__(self, name=None, email=None):
        self.name = name
        self.email = email

    def __repr__(self):
        return '<User %r>' % (self.name)

    def serialize(self):
        d = Serializer.serialize(self)
        return d

class Cred(Base):
    __tablename__ = 'creds'
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    token = Column(String(250))
    refresh_token = Column(String(250))
    token_uri = Column(String(250))
    client_id = Column(String(250))
    client_secret = Column(String(250))
    scopes = Column(String(250))

    def __init__(self, token=None, refresh_token=None, token_uri=None,
                 client_id=None, client_secret=None, scopes=None):
        self.token = token
        self.refresh_token = refresh_token
        self.token_uri = token_uri
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes

    def __repr__(self):
        return '<Cred %r>' % (self.id)

    def serialize(self):
        d = Serializer.serialize(self)
        return d

class Video(Base):
    __tablename__ = 'videos'
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    youtube_id = Column(String(250), unique=True)
    channel_id = Column(String(250), unique=True)
    title = Column(String(250))

    def __init__(self, youtube_id=None, channel_id=None, title=None):
        self.youtube_id = youtube_id
        self.channel_id = channel_id
        self.title = title

    def __repr__(self):
        return '<Video %r>' % self.youtube_id

    def serialize(self):
        d = Serializer.serialize(self)
        return d


class Tag(Base):
    __tablename__ = 'tags'
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    video_id = Column(String(250), primary_key=True)
    title = Column(String(250))
    # video = relationship("Video", foreign_keys=Video.id)

    def __init__(self, title=None, video_id=None):
        self.title = title
        self.video_id = video_id

    def __repr__(self):
        return '<Tag %r>' % (self.title)

    def serialize(self):
        d = Serializer.serialize(self)
        return d


class Statistic(Base):
    __tablename__ = 'statistics'
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    commentCount = Column(Integer)
    dislikeCount = Column(Integer)
    favoriteCount = Column(Integer)
    likeCount = Column(Integer)
    viewCount = Column(Integer)

    def __init__(self, commentCount=None, dislikeCount=None, favoriteCount=None, likeCount=None, viewCount=None):
        self.commentCount = commentCount
        self.dislikeCount = dislikeCount
        self.favoriteCount = favoriteCount
        self.likeCount = likeCount
        self.viewCount = viewCount

    def __repr__(self):
        return '<Statistic %r>' % (self.id)

    def serialize(self):
        d = Serializer.serialize(self)
        return d

