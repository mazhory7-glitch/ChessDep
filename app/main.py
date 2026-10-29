from __future__ import annotations
import os, secrets, hashlib, hmac, time, json, random, colorsys
from datetime import datetime, timezone, timedelta
from typing import Optional
import chess
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, select, func, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

DB_URL=os.getenv('DATABASE_URL','sqlite:///./chessdep.db')
engine=create_engine(DB_URL,connect_args={'check_same_thread':False} if DB_URL.startswith('sqlite') else {},pool_pre_ping=True)
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id:Mapped[int]=mapped_column(primary_key=True); login:Mapped[str]=mapped_column(String(16),unique=True,index=True); email:Mapped[str]=mapped_column(String(254),unique=True,index=True); password:Mapped[str]=mapped_column(String(255)); role:Mapped[str]=mapped_column(String(12),default='player'); balance:Mapped[int]=mapped_column(Integer,default=1000); elo:Mapped[int]=mapped_column(Integer,default=1200); session_version:Mapped[int]=mapped_column(Integer,default=0); joined:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc)); last_daily:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
class Skin(Base):
    __tablename__='skins'
    id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(80)); kind:Mapped[str]=mapped_column(String(12)); piece:Mapped[str]=mapped_column(String(12)); rarity:Mapped[str]=mapped_column(String(16)); value:Mapped[int]=mapped_column(Integer); color:Mapped[str]=mapped_column(String(16),default='#f5f5f5'); light:Mapped[str]=mapped_column(String(16),default='#454f77'); dark:Mapped[str]=mapped_column(String(16),default='#262e4d'); target:Mapped[bool]=mapped_column(Boolean,default=True); collection:Mapped[str]=mapped_column(String(80),default='Genesis')
class Item(Base):
    __tablename__='items'
    id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True); skin_id:Mapped[int]=mapped_column(ForeignKey('skins.id')); wear:Mapped[float]=mapped_column(Float,default=0); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc)); equipped:Mapped[bool]=mapped_column(Boolean,default=False)
class Ledger(Base):
    __tablename__='ledger'
    id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True); amount:Mapped[int]=mapped_column(Integer); label:Mapped[str]=mapped_column(String(120)); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Listing(Base):
    __tablename__='listings'
    id:Mapped[int]=mapped_column(primary_key=True); item_id:Mapped[int]=mapped_column(ForeignKey('items.id'),unique=True); seller_id:Mapped[int]=mapped_column(ForeignKey('users.id')); price:Mapped[int]=mapped_column(Integer); status:Mapped[str]=mapped_column(String(12),default='active'); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Gift(Base):
    __tablename__='gifts'
    id:Mapped[int]=mapped_column(primary_key=True); item_id:Mapped[int]=mapped_column(ForeignKey('items.id')); sender_id:Mapped[int]=mapped_column(ForeignKey('users.id')); recipient_id:Mapped[int]=mapped_column(ForeignKey('users.id')); note:Mapped[str]=mapped_column(String(140),default=''); seen:Mapped[bool]=mapped_column(Boolean,default=False); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Case(Base):
    __tablename__='cases'
    id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(80)); price:Mapped[int]=mapped_column(Integer); kind:Mapped[str]=mapped_column(String(12))
class Match(Base):
    __tablename__='matches'
    equipment:Mapped[str]=mapped_column(Text,default='{}')
    id:Mapped[int]=mapped_column(primary_key=True); white_id:Mapped[int]=mapped_column(ForeignKey('users.id')); black_id:Mapped[int]=mapped_column(ForeignKey('users.id')); control:Mapped[str]=mapped_column(String(8)); fen:Mapped[str]=mapped_column(Text); pgn:Mapped[str]=mapped_column(Text,default=''); status:Mapped[str]=mapped_column(String(12),default='active'); result:Mapped[str]=mapped_column(String(30),default=''); dep_white:Mapped[int]=mapped_column(Integer,default=0); dep_black:Mapped[int]=mapped_column(Integer,default=0); dep_used:Mapped[bool]=mapped_column(Boolean,default=False); white_ms:Mapped[int]=mapped_column(Integer,default=180000); black_ms:Mapped[int]=mapped_column(Integer,default=180000); increment_ms:Mapped[int]=mapped_column(Integer,default=2000); clock_updated:Mapped[float]=mapped_column(Float,default=time.time); bot_game:Mapped[bool]=mapped_column(Boolean,default=False); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class MatchQueue(Base):
    __tablename__='match_queue'
    id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True); control:Mapped[str]=mapped_column(String(8)); status:Mapped[str]=mapped_column(String(12),default='waiting'); match_id:Mapped[Optional[int]]=mapped_column(ForeignKey('matches.id'),nullable=True); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class ChatMessage(Base):
    __tablename__='chat_messages'
    id:Mapped[int]=mapped_column(primary_key=True); match_id:Mapped[int]=mapped_column(ForeignKey('matches.id'),index=True); user_id:Mapped[int]=mapped_column(ForeignKey('users.id')); body:Mapped[str]=mapped_column(String(500)); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class AdminLog(Base):
    __tablename__='admin_log'
    id:Mapped[int]=mapped_column(primary_key=True); admin_id:Mapped[int]=mapped_column(Integer); action:Mapped[str]=mapped_column(String(120)); detail:Mapped[str]=mapped_column(Text); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
Base.metadata.create_all(engine)
with engine.begin() as _conn:
    if engine.dialect.name=='sqlite':
      _columns={row[1] for row in _conn.exec_driver_sql('PRAGMA table_info(users)').fetchall()}
      if 'session_version' not in _columns:_conn.exec_driver_sql('ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0')
      _match_columns={row[1] for row in _conn.exec_driver_sql('PRAGMA table_info(matches)').fetchall()}
      for _name,_definition in [('equipment',"TEXT NOT NULL DEFAULT '{}'"),('white_ms','INTEGER NOT NULL DEFAULT 180000'),('black_ms','INTEGER NOT NULL DEFAULT 180000'),('increment_ms','INTEGER NOT NULL DEFAULT 2000'),('clock_updated','FLOAT NOT NULL DEFAULT 0'),('bot_game','BOOLEAN NOT NULL DEFAULT 0')]:
        if _name not in _match_columns:_conn.exec_driver_sql(f'ALTER TABLE matches ADD COLUMN {_name} {_definition}')
      _conn.exec_driver_sql('UPDATE matches SET clock_updated=? WHERE clock_updated=0',(time.time(),))
ph=PasswordHasher(); app=FastAPI(title='ChessDep')
app.mount('/static',StaticFiles(directory='/app/app/static'),name='static')
_session_secret=None
def session_secret():
    global _session_secret
    if _session_secret:return _session_secret
    configured=os.getenv('SESSION_SECRET','').strip()
    if configured and len(configured)>=32 and configured not in ('change-me-to-a-long-random-secret','please-change-this-secret'):
      _session_secret=configured.encode();return _session_secret
    secret_path='/data/session_secret' if os.path.isdir('/data') else '.session_secret'
    try:
      with open(secret_path,'rb') as f:_session_secret=f.read().strip()
      if len(_session_secret)>=32:return _session_secret
    except FileNotFoundError:pass
    _session_secret=secrets.token_bytes(48)
    os.makedirs(os.path.dirname(secret_path) or '.',exist_ok=True)
    fd=os.open(secret_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as f:f.write(_session_secret)
    return _session_secret
RARITIES=[('Обычный','обычный','#9aa4b2',20),('Необычный','необычный','#38e8ff',60),('Редкий','редкий','#8b5cf6',150),('Эпический','эпический','#ffc93c',500),('Легендарный','легендарный','#ff7847',1500),('Мифический','мифический','#ff5470',5000)]
CASE_RARITY_WEIGHTS={'обычный':799200,'необычный':159800,'редкий':32000,'эпический':6400,'легендарный':1280,'мифический':256}
PIECES=[('Пешка','pawn','♙'),('Конь','knight','♘'),('Слон','bishop','♗'),('Ладья','rook','♖'),('Ферзь','queen','♕'),('Король','king','♔')]
FIGURE_VALUES={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9}
def dep_chance(source_type:int,target_type:int)->float:
    if source_type not in FIGURE_VALUES or target_type not in FIGURE_VALUES or FIGURE_VALUES[target_type]<=FIGURE_VALUES[source_type]:
      raise ValueError('Цель должна быть фигурой большей ценности.')
    return FIGURE_VALUES[source_type]/FIGURE_VALUES[target_type]
def db():
    with Session(engine) as s: yield s
def token(user_id:int,version:int=0):
    raw=f'{user_id}:{int(time.time())+86400}:{version}'
    sig=hmac.new(session_secret(),raw.encode(),hashlib.sha256).hexdigest()
    return raw+'.'+sig
def current(request:Request,s:Session=Depends(db)):
    t=request.cookies.get('session','')
    try:
        raw,sig=t.rsplit('.',1); uid,exp,version=raw.split(':'); good=hmac.compare_digest(sig,hmac.new(session_secret(),raw.encode(),hashlib.sha256).hexdigest()) and int(exp)>time.time()
    except Exception: good=False
    u=s.get(User,int(uid)) if good else None
    if not u or int(version)!=u.session_version: raise HTTPException(401,'Войдите в аккаунт.')
    return u
def admin(u=Depends(current)):
    if u.role!='admin': raise HTTPException(404,'Страница не найдена.')
    return u
def wallet(s,u,amount,label):
    # One conditional SQL UPDATE is the balance guard, including under concurrent requests.
    result=s.execute(update(User).where(User.id==u.id,User.balance+amount>=0).values(balance=User.balance+amount))
    if result.rowcount!=1: raise HTTPException(400,'Недостаточно кристаллов.')
    s.refresh(u);s.add(Ledger(user_id=u.id,amount=amount,label=label))
def skin_json(skin): return {'id':skin.id,'name':skin.name,'kind':skin.kind,'piece':skin.piece,'rarity':skin.rarity,'value':skin.value,'color':skin.color,'light':skin.light,'dark':skin.dark,'collection':skin.collection,'target':skin.target}
def ensure_unlisted(s,it):
    if s.scalar(select(Listing.id).where(Listing.item_id==it.id,Listing.status=='active')):
      raise HTTPException(400,'Сначала снимите предмет с продажи.')
def equipment_snapshot(s,white_id,black_id):
    result={}
    for side,uid in [('white',white_id),('black',black_id)]:
      result[side]={}
      for it in s.scalars(select(Item).where(Item.user_id==uid,Item.equipped==True)):
        skin=s.get(Skin,it.skin_id);result[side][skin.piece]=skin_json(skin)
    return json.dumps(result)
def item_json(s,it):
    sk=s.get(Skin,it.skin_id); return {'id':it.id,'wear':it.wear,'equipped':it.equipped,'skin':skin_json(sk)}
def seed():
  with Session(engine) as s:
    if s.scalar(select(func.count(Skin.id)))==0:
      figure_variants=[('Мел','обычный',20),('Иней','редкий',150),('Снег','эпический',500)]
      for pname,piece,glyph in PIECES:
        for label,rarity,value in figure_variants:
          skin_colors={'Мел':'#ff4b59','Иней':'#398cff','Снег':'#37e890'}
          s.add(Skin(name=f'{pname} | {label}',kind='figure',piece=piece,rarity=rarity,value=value,color=skin_colors[label],target=True))
      board_colors={'Бумага':('#c9b99b','#635443'),'Фарфор':('#d9f2ff','#51738f'),'Мрамор':('#e6e8ef','#4b5368'),'Альбион':('#f2e4bd','#4c386b')}
      for name,rarity in [('Бумага','обычный'),('Фарфор','необычный'),('Мрамор','эпический'),('Альбион','мифический')]:
        r=next(x for x in RARITIES if x[1]==rarity);light,dark=board_colors[name];s.add(Skin(name=name,kind='board',piece='board',rarity=rarity,value=r[3],light=light,dark=dark,target=True))
      s.add_all([Case(name='Genesis: фигуры',price=100,kind='figure'),Case(name='Genesis: доски',price=250,kind='board')]);s.commit()
    # Apply the named Genesis palettes to existing persistent installs too.
    palette={'Мел':'#ff4b59','Иней':'#398cff','Снег':'#37e890'}
    boards={'Бумага':('#c9b99b','#635443'),'Фарфор':('#d9f2ff','#51738f'),'Мрамор':('#e6e8ef','#4b5368'),'Альбион':('#f2e4bd','#4c386b')}
    for skin in s.scalars(select(Skin)).all():
      if skin.kind=='figure':
        variant=skin.name.rsplit(' | ',1)[-1]
        if variant in palette:
          colors={'pawn':['#ff4b59','#398cff','#37e890'],'knight':['#ff843d','#55d5ff','#a4f542'],'bishop':['#ed478d','#7567ff','#1ed5ae'],'rook':['#e85c35','#4579df','#7cde51'],'queen':['#ff66a6','#a16bff','#2df7c5'],'king':['#ffb23f','#4bbdeb','#60ca6c']}
          skin.color=colors.get(skin.piece,list(palette.values()))[list(palette).index(variant)]
        else:
          rank=next((i for i,r in enumerate(RARITIES) if r[1]==skin.rarity),0)
          piece_index=next((i for i,p in enumerate(PIECES) if p[1]==skin.piece),0)
          rgb=colorsys.hsv_to_rgb((rank/6+piece_index*.025)%1,.72,1)
          skin.color='#'+''.join(f'{round(c*255):02x}' for c in rgb)
      elif skin.name in boards:skin.light,skin.dark=boards[skin.name]
    # The bot is an internal participant and is never eligible for login.
    if not s.scalar(select(User).where(User.login=='ChessDepBot')):
      s.add(User(login='ChessDepBot',email='chessdep-bot@invalid.local',password=ph.hash(secrets.token_urlsafe(32)),role='bot',balance=0,elo=1200))
    s.commit()
seed()
class Credentials(BaseModel): login:str; email:str=''; password:str
class IdBody(BaseModel): id:int
class PriceBody(BaseModel): item_id:int; price:int=Field(ge=1,le=10000000)
class GiftBody(BaseModel): item_id:int; login:str; note:str=Field(default='',max_length=140)
class MoveBody(BaseModel): uci:str
class ChatBody(BaseModel): body:str=Field(min_length=1,max_length=500)
class DepBody(BaseModel): square:str; target:str
class UpgradeBody(BaseModel): item_ids:list[int]=Field(min_length=1,max_length=10); target_skin:int
class AdminBalance(BaseModel): amount:int; comment:str=Field(min_length=3,max_length=200)

@app.post('/api/register')
def register(b:Credentials,response:Response,s:Session=Depends(db)):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,16}',b.login): raise HTTPException(400,'Логин: 3–16 символов, латиница, цифры, _ или -.')
    if '@' not in b.email or len(b.password)<8: raise HTTPException(400,'Проверьте email и пароль (не менее 8 символов).')
    if s.scalar(select(User).where((User.login==b.login)|(User.email==b.email))): raise HTTPException(409,'Логин или email уже зарегистрирован.')
    u=User(login=b.login,email=b.email,password=ph.hash(b.password));u.role='player';s.add(u);s.flush();s.add(Ledger(user_id=u.id,amount=1000,label='Бонус за регистрацию'));s.commit();response.set_cookie('session',token(u.id,u.session_version),httponly=True,samesite='lax',secure=False,max_age=86400);return {'ok':True}
@app.post('/api/login')
def login(b:Credentials,response:Response,s:Session=Depends(db)):
    u=s.scalar(select(User).where(User.login==b.login))
    try: valid=u and ph.verify(u.password,b.password)
    except VerifyMismatchError: valid=False
    if not valid: raise HTTPException(401,'Неверный логин или пароль.')
    response.set_cookie('session',token(u.id,u.session_version),httponly=True,samesite='lax',secure=False,max_age=86400);return {'ok':True}
@app.post('/api/logout')
def logout(response:Response,u=Depends(current),s:Session=Depends(db)):
    u.session_version+=1;s.commit();response.delete_cookie('session');return {'ok':True}
@app.get('/api/me')
def me(u=Depends(current),s:Session=Depends(db)):
    return {'id':u.id,'login':u.login,'role':u.role,'balance':u.balance,'elo':u.elo,'new_gifts':s.scalar(select(func.count(Gift.id)).where(Gift.recipient_id==u.id,Gift.seen==False))}
@app.post('/api/daily')
def daily(u=Depends(current),s:Session=Depends(db)):
    now=datetime.now(timezone.utc)
    if u.last_daily and (now-u.last_daily.replace(tzinfo=timezone.utc)).total_seconds()<86400: raise HTTPException(400,'Ежедневный бонус ещё не доступен.')
    u.last_daily=now;wallet(s,u,200,'Ежедневный бонус');s.commit();return {'balance':u.balance}
@app.get('/api/inventory')
def inventory(u=Depends(current),s:Session=Depends(db)):
    items=s.scalars(select(Item).where(Item.user_id==u.id)).all();return [item_json(s,i) for i in items]
@app.post('/api/equip')
def equip(b:IdBody,u=Depends(current),s:Session=Depends(db)):
    it=s.get(Item,b.id)
    if not it or it.user_id!=u.id: raise HTTPException(404,'Предмет не найден.')
    ensure_unlisted(s,it)
    sk=s.get(Skin,it.skin_id)
    for old in s.scalars(select(Item).where(Item.user_id==u.id,Item.equipped==True)).all():
      if s.get(Skin,old.skin_id).piece==sk.piece:old.equipped=False
    it.equipped=True;s.commit();return {'ok':True}
@app.post('/api/unequip')
def unequip(b:IdBody,u=Depends(current),s:Session=Depends(db)):
    it=s.get(Item,b.id)
    if not it or it.user_id!=u.id:raise HTTPException(404,'Предмет не найден.')
    it.equipped=False;s.commit();return {'ok':True}
@app.get('/api/cases')
def cases(s:Session=Depends(db)): return [{'id':c.id,'name':c.name,'price':c.price} for c in s.scalars(select(Case)).all()]
@app.get('/api/cases/{case_id}/contents')
def case_contents(case_id:int,s:Session=Depends(db)):
    c=s.get(Case,case_id)
    if not c:raise HTTPException(404,'Кейс не найден.')
    pool=s.scalars(select(Skin).where(Skin.kind==c.kind)).all();total=sum(CASE_RARITY_WEIGHTS.get(sk.rarity,0) for sk in pool)
    return {'case':c.name,'price':c.price,'drops':[{'skin':skin_json(sk),'chance':CASE_RARITY_WEIGHTS.get(sk.rarity,0)/total if total else 0} for sk in pool]}
@app.post('/api/cases/{case_id}/open')
def open_case(case_id:int,u=Depends(current),s:Session=Depends(db)):
    c=s.get(Case,case_id)
    if not c:raise HTTPException(404,'Кейс не найден.')
    wallet(s,u,-c.price,f'Покупка кейса: {c.name}')
    pool=s.scalars(select(Skin).where(Skin.kind==c.kind)).all()
    # Higher rarity has lower probability; server CSPRNG chooses outcome.
    weights=[CASE_RARITY_WEIGHTS.get(sk.rarity,1) for sk in pool]; sk=secrets.SystemRandom().choices(pool,weights=weights,k=1)[0]
    wear=secrets.randbelow(1000001)/1000000;it=Item(user_id=u.id,skin_id=sk.id,wear=wear);s.add(it);s.flush()
    reel=[]
    for _ in range(60):
      filler=secrets.choice(pool);reel.append(skin_json(filler))
    win_index=47;reel[win_index]=skin_json(sk)
    s.commit();return {'item':item_json(s,it),'balance':u.balance,'reel':reel,'win_index':win_index}
@app.post('/api/market/list')
def list_item(b:PriceBody,u=Depends(current),s:Session=Depends(db)):
    it=s.get(Item,b.item_id)
    if not it or it.user_id!=u.id:raise HTTPException(404,'Предмет не найден.')
    if s.scalar(select(Listing).where(Listing.seller_id==u.id,Listing.status=='active')) and s.scalar(select(func.count(Listing.id)).where(Listing.seller_id==u.id,Listing.status=='active'))>=50:raise HTTPException(400,'Достигнут лимит в 50 лотов.')
    if s.scalar(select(Listing).where(Listing.item_id==it.id,Listing.status=='active')):raise HTTPException(400,'Предмет уже выставлен.')
    it.equipped=False;s.add(Listing(item_id=it.id,seller_id=u.id,price=b.price));s.commit();return {'ok':True}
@app.get('/api/market')
def market(s:Session=Depends(db)):
    rows=s.execute(select(Listing,Item,Skin,User).join(Item,Listing.item_id==Item.id).join(Skin,Item.skin_id==Skin.id).join(User,Listing.seller_id==User.id).where(Listing.status=='active').order_by(Listing.created.desc()).limit(100)).all()
    return [{'id':l.id,'price':l.price,'seller':user.login,'item':item_json(s,it)} for l,it,sk,user in rows]
@app.post('/api/market/buy/{listing_id}')
def buy(listing_id:int,u=Depends(current),s:Session=Depends(db)):
    l=s.scalar(select(Listing).where(Listing.id==listing_id,Listing.status=='active'))
    if not l:raise HTTPException(404,'Лот уже недоступен.')
    if l.seller_id==u.id:raise HTTPException(400,'Нельзя купить собственный лот.')
    seller=s.get(User,l.seller_id);it=s.get(Item,l.item_id);wallet(s,u,-l.price,'Покупка на маркете');wallet(s,seller,l.price*95//100,'Продажа на маркете');it.user_id=u.id;l.status='sold';s.commit();return {'ok':True,'balance':u.balance}
@app.post('/api/market/cancel/{listing_id}')
def cancel_listing(listing_id:int,u=Depends(current),s:Session=Depends(db)):
    l=s.get(Listing,listing_id)
    if not l or l.seller_id!=u.id or l.status!='active':raise HTTPException(404,'Активный лот не найден.')
    l.status='removed';s.commit();return {'ok':True}
@app.post('/api/gifts')
def gift(b:GiftBody,u=Depends(current),s:Session=Depends(db)):
    it=s.get(Item,b.item_id);recipient=s.scalar(select(User).where(User.login==b.login))
    if not it or it.user_id!=u.id:raise HTTPException(404,'Предмет не найден.')
    if not recipient or recipient.id==u.id:raise HTTPException(400,'Укажите логин другого игрока.')
    ensure_unlisted(s,it)
    it.user_id=recipient.id;it.equipped=False;s.add(Gift(item_id=it.id,sender_id=u.id,recipient_id=recipient.id,note=b.note));s.commit();return {'ok':True}
@app.get('/api/gifts')
def gifts(u=Depends(current),s:Session=Depends(db)):
    rows=s.scalars(select(Gift).where((Gift.recipient_id==u.id)|(Gift.sender_id==u.id)).order_by(Gift.created.desc())).all();out=[]
    for g in rows:
      is_incoming=g.recipient_id==u.id
      out.append({'from':s.get(User,g.sender_id).login,'to':s.get(User,g.recipient_id).login,'note':g.note,'item':item_json(s,s.get(Item,g.item_id)),'seen':g.seen,'incoming':is_incoming})
      if is_incoming:g.seen=True
    s.commit();return out
@app.get('/api/skins')
def skins(s:Session=Depends(db)):return [skin_json(k) for k in s.scalars(select(Skin)).all()]
@app.get('/api/leaderboard')
def leaderboard(sort:str='elo',s:Session=Depends(db)):
    col=User.balance if sort=='balance' else User.elo
    return [{'place':i+1,'login':u.login,'elo':u.elo,'balance':u.balance} for i,u in enumerate(s.scalars(select(User).where(User.role!='bot').order_by(col.desc()).limit(100)).all())]
@app.get('/api/ledger')
def ledger(u=Depends(current),s:Session=Depends(db)):return [{'amount':x.amount,'label':x.label,'created':x.created.isoformat()} for x in s.scalars(select(Ledger).where(Ledger.user_id==u.id).order_by(Ledger.created.desc()).limit(100)).all()]
@app.post('/api/upgrade')
def upgrade(b:UpgradeBody,u=Depends(current),s:Session=Depends(db)):
    its=[s.get(Item,i) for i in set(b.item_ids)]
    if len(its)!=len(b.item_ids) or any(not i or i.user_id!=u.id for i in its):raise HTTPException(400,'Выберите только свои предметы.')
    for it in its:ensure_unlisted(s,it)
    target=s.get(Skin,b.target_skin)
    if not target or not target.target:raise HTTPException(400,'Этот скин нельзя выбрать целью.')
    chance=sum(s.get(Skin,i.skin_id).value for i in its)/target.value*.95
    if not .01<=chance<=.8:raise HTTPException(400,'Шанс вне допустимого диапазона.')
    win=secrets.randbelow(1000000)<int(chance*1000000)
    for it in its:s.delete(it)
    result=None
    if win:result=Item(user_id=u.id,skin_id=target.id,wear=secrets.randbelow(1000001)/1000000);s.add(result)
    s.commit();return {'won':win,'chance':chance,'item':item_json(s,result) if result else None}

# Minimal authoritative chess endpoints: FEN, legal move validation and server-side checkmate/stalemate.
@app.post('/api/matches')
def create_match(control:str='3+2',u=Depends(current),s:Session=Depends(db)):
    if control not in ('3+2','5+0','10+0'):raise HTTPException(400,'Неизвестный контроль времени.')
    active=s.scalar(select(Match).where(Match.status=='active',((Match.white_id==u.id)|(Match.black_id==u.id))))
    if active: return {'id':active.id,'fen':active.fen,'status':active.status}
    entry=s.scalar(select(MatchQueue).where(MatchQueue.user_id==u.id))
    if entry and entry.status=='paired':
      m=s.get(Match,entry.match_id);return {'id':m.id,'fen':m.fen,'status':'paired'}
    if entry and entry.status=='waiting' and entry.control!=control:entry.control=control;entry.created=datetime.now(timezone.utc)
    if not entry:entry=MatchQueue(user_id=u.id,control=control,status='waiting');s.add(entry);s.flush()
    opponent=s.scalar(select(MatchQueue).where(MatchQueue.control==control,MatchQueue.status=='waiting',MatchQueue.user_id!=u.id).order_by(MatchQueue.created).with_for_update())
    if not opponent:
      s.commit();return {'status':'searching','control':control}
    m=Match(white_id=opponent.user_id,black_id=u.id,control=control,fen=chess.STARTING_FEN,pgn='',white_ms=initial_ms(control),black_ms=initial_ms(control),increment_ms=2000 if control=='3+2' else 0,clock_updated=time.time(),equipment=equipment_snapshot(s,opponent.user_id,u.id));s.add(m);s.flush()
    opponent.status='paired';opponent.match_id=m.id;entry.status='paired';entry.match_id=m.id;s.commit()
    return {'id':m.id,'fen':m.fen,'status':'paired'}
def initial_ms(control):return {'3+2':180000,'5+0':300000,'10+0':600000}[control]
@app.post('/api/matches/bot')
def create_bot_match(control:str='3+2',u=Depends(current),s:Session=Depends(db)):
    if control not in ('3+2','5+0','10+0'):raise HTTPException(400,'Неизвестный контроль времени.')
    active=s.scalar(select(Match).where(Match.status=='active',((Match.white_id==u.id)|(Match.black_id==u.id))))
    if active:return {'id':active.id,'fen':active.fen,'status':active.status}
    bot=s.scalar(select(User).where(User.role=='bot'))
    if not bot:
      bot=User(login='ChessDepBot',email='chessdep-bot@invalid.local',password=ph.hash(secrets.token_urlsafe(32)),role='bot',balance=0,elo=1200);s.add(bot);s.flush()
    m=Match(white_id=u.id,black_id=bot.id,control=control,fen=chess.STARTING_FEN,pgn='',white_ms=initial_ms(control),black_ms=initial_ms(control),increment_ms=2000 if control=='3+2' else 0,clock_updated=time.time(),bot_game=True,equipment=equipment_snapshot(s,u.id,bot.id))
    s.add(m);s.commit();return {'id':m.id,'fen':m.fen,'status':'paired','bot':True}
def clock_left(m,board):
    white,black=m.white_ms,m.black_ms
    elapsed=max(0,int((time.time()-m.clock_updated)*1000)) if m.status=='active' else 0
    if board.turn:white=max(0,white-elapsed)
    else:black=max(0,black-elapsed)
    return white,black
def charge_clock(m,board,add_increment=False):
    now=time.time();elapsed=max(0,int((now-m.clock_updated)*1000))
    if board.turn:
      m.white_ms=max(0,m.white_ms-elapsed)
      if m.white_ms==0:return False
      if add_increment:m.white_ms+=m.increment_ms
    else:
      m.black_ms=max(0,m.black_ms-elapsed)
      if m.black_ms==0:return False
      if add_increment:m.black_ms+=m.increment_ms
    m.clock_updated=now;return True
def choose_bot_move(board):
    values={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9,chess.KING:20}
    scored=[]
    for move in board.legal_moves:
      score=secrets.randbelow(100)/100
      if board.is_capture(move):
        victim=board.piece_at(move.to_square)
        if board.is_en_passant(move):victim=chess.Piece(chess.PAWN,not board.turn)
        attacker=board.piece_at(move.from_square)
        score+=4+(values[victim.piece_type] if victim else 0)-(values[attacker.piece_type]*.12 if attacker else 0)
      board.push(move);score+=8 if board.is_checkmate() else 1.2 if board.is_check() else 0;board.pop()
      f=chess.square_file(move.to_square);r=chess.square_rank(move.to_square)
      score+=max(0,2-(abs(3.5-f)+abs(3.5-r))*.25)
      scored.append((score,move))
    scored.sort(key=lambda x:x[0],reverse=True)
    return secrets.choice([x[1] for x in scored[:min(4,len(scored))]])
@app.get('/api/matches/queue')
def queue_status(u=Depends(current),s:Session=Depends(db)):
    entry=s.scalar(select(MatchQueue).where(MatchQueue.user_id==u.id))
    if not entry:return {'status':'idle'}
    if entry.status=='paired':
      m=s.get(Match,entry.match_id);return {'status':'paired','id':m.id,'fen':m.fen,'control':m.control}
    return {'status':entry.status,'control':entry.control}
@app.delete('/api/matches/queue')
def queue_cancel(u=Depends(current),s:Session=Depends(db)):
    entry=s.scalar(select(MatchQueue).where(MatchQueue.user_id==u.id,MatchQueue.status=='waiting'))
    if entry:entry.status='cancelled';s.commit()
    return {'status':'idle'}
@app.get('/api/matches/ongoing')
def ongoing(u=Depends(current),s:Session=Depends(db)):
    rows=s.scalars(select(Match).where(Match.status=='active').order_by(Match.created.desc()).limit(100)).all();out=[]
    for m in rows:
      board=chess.Board(m.fen);out.append({'id':m.id,'white':s.get(User,m.white_id).login,'black':s.get(User,m.black_id).login,'control':m.control,'ply':board.ply(),'deps':m.dep_white+m.dep_black})
    return out
@app.get('/api/matches/{mid}/chat')
def match_chat(mid:int,u=Depends(current),s:Session=Depends(db)):
    m=s.get(Match,mid)
    if not m:raise HTTPException(404,'Партия не найдена.')
    rows=s.scalars(select(ChatMessage).where(ChatMessage.match_id==mid).order_by(ChatMessage.created.desc()).limit(100)).all()
    rows.reverse();out=[]
    for x in rows:
      role='зритель' if x.user_id not in (m.white_id,m.black_id) else ('белые' if x.user_id==m.white_id else 'чёрные')
      out.append({'login':s.get(User,x.user_id).login,'role':role,'body':x.body,'created':x.created.isoformat()})
    return out
@app.post('/api/matches/{mid}/chat')
def send_match_chat(mid:int,b:ChatBody,u=Depends(current),s:Session=Depends(db)):
    if not s.get(Match,mid):raise HTTPException(404,'Партия не найдена.')
    body=b.body.strip()
    if not body:raise HTTPException(400,'Сообщение не может быть пустым.')
    s.add(ChatMessage(match_id=mid,user_id=u.id,body=body));s.commit();return {'ok':True}
@app.get('/api/matches/{mid}')
def match_state(mid:int,u=Depends(current),s:Session=Depends(db)):
    m=s.get(Match,mid)
    if not m:raise HTTPException(404,'Партия не найдена.')
    board=chess.Board(m.fen);white_ms,black_ms=clock_left(m,board)
    if m.status=='active' and (white_ms==0 or black_ms==0):
      m.status='finished';m.result='Время вышло · Победа чёрных' if white_ms==0 else 'Время вышло · Победа белых';m.white_ms=white_ms;m.black_ms=black_ms;s.commit()
    return {'id':m.id,'fen':m.fen,'status':m.status,'result':m.result,'turn':'white' if board.turn else 'black','check':board.is_check(),'legal':[x.uci() for x in board.legal_moves],'pgn':m.pgn,'dep_white':m.dep_white,'dep_black':m.dep_black,'dep_used':m.dep_used,'white_id':m.white_id,'black_id':m.black_id,'white':s.get(User,m.white_id).login,'black':s.get(User,m.black_id).login,'white_ms':white_ms,'black_ms':black_ms,'clock_running':m.status=='active','control':m.control,'bot_game':m.bot_game,'equipment':json.loads(m.equipment or '{}')}
@app.post('/api/matches/{mid}/move')
def move(mid:int,b:MoveBody,u=Depends(current),s:Session=Depends(db)):
    m=s.get(Match,mid)
    if not m or m.status!='active':raise HTTPException(404,'Активная партия не найдена.')
    if m.white_id!=u.id and m.black_id!=u.id:raise HTTPException(403,'Вы не участник партии.')
    board=chess.Board(m.fen)
    if m.bot_game and u.id==m.white_id and not board.turn:raise HTTPException(403,'Сейчас ход бота.')
    if (board.turn and m.white_id!=u.id) or (not board.turn and m.black_id!=u.id):raise HTTPException(403,'Сейчас ход соперника.')
    if b.uci not in [x.uci() for x in board.legal_moves]:raise HTTPException(400,'Недопустимый ход.')
    if not charge_clock(m,board,add_increment=True):
      m.status='finished';m.result='Время вышло';s.commit();raise HTTPException(400,'Время вышло.')
    board.push_uci(b.uci);m.fen=board.fen();m.pgn=(m.pgn+' '+b.uci).strip();m.dep_used=False
    if m.bot_game and not board.is_game_over():
      bot_move=choose_bot_move(board)
      if charge_clock(m,board,add_increment=True):
        board.push(bot_move);m.fen=board.fen();m.pgn=(m.pgn+' '+bot_move.uci()).strip()
      else:m.status='finished';m.result='Время вышло'
    if board.is_checkmate() or board.is_stalemate() or board.is_insufficient_material() or board.can_claim_threefold_repetition() or board.can_claim_fifty_moves():m.status='finished';m.result='Мат' if board.is_checkmate() else 'Ничья'
    s.commit();return {'fen':m.fen,'status':m.status,'result':m.result}
@app.post('/api/matches/{mid}/dep')
def dep(mid:int,b:DepBody,u=Depends(current),s:Session=Depends(db)):
    m=s.get(Match,mid)
    if not m or m.status!='active':raise HTTPException(404,'Активная партия не найдена.')
    if u.id not in (m.white_id,m.black_id):raise HTTPException(403,'Вы не участник партии.')
    board=chess.Board(m.fen); color=board.turn
    if (color and m.white_id!=u.id) or (not color and m.black_id!=u.id):raise HTTPException(403,'Сейчас ход соперника.')
    count=m.dep_white if color else m.dep_black
    if m.dep_used:raise HTTPException(400,'За этот ход деп уже использован.')
    if count>=10:raise HTTPException(400,'Достигнут лимит депов за партию.')
    try: square=chess.parse_square(b.square); target={'knight':chess.KNIGHT,'bishop':chess.BISHOP,'rook':chess.ROOK,'queen':chess.QUEEN}[b.target]
    except Exception:raise HTTPException(400,'Неверная фигура или цель депа.')
    piece=board.piece_at(square)
    if not piece or piece.color!=color or piece.piece_type==chess.KING:raise HTTPException(400,'Выберите свою фигуру, кроме короля.')
    try:chance=dep_chance(piece.piece_type,target)
    except ValueError:raise HTTPException(400,'Нет цели большей ценности.')
    # Neither possible result may give check to the opponent.
    outcomes=[]
    for success in (False,True):
      candidate=board.copy();candidate.remove_piece_at(square)
      if success:candidate.set_piece_at(square,chess.Piece(target,color))
      candidate.turn=not color
      outcomes.append(candidate)
    if any(candidate.is_check() for candidate in outcomes):raise HTTPException(400,'Даст шах сопернику.')
    if not charge_clock(m,board):
      m.status='finished';m.result='Время вышло';s.commit();raise HTTPException(400,'Время вышло.')
    won=secrets.randbelow(1000000)<int(chance*1000000)
    board.remove_piece_at(square)
    if won:board.set_piece_at(square,chess.Piece(target,color))
    # A dep changes the position but does not hand the move to the opponent.
    # The player who deped must still make a legal chess move this turn.
    m.fen=board.fen();m.dep_used=True
    if color:m.dep_white+=1
    else:m.dep_black+=1
    m.pgn=(m.pgn+f" DEP:{b.square}:{b.target}:{'win' if won else 'loss'}:{chance:.6f}").strip()
    if board.is_checkmate() or board.is_stalemate() or board.is_insufficient_material():m.status='finished';m.result='Мат' if board.is_checkmate() else 'Ничья'
    s.commit();return {'won':won,'chance':chance,'fen':m.fen,'status':m.status,'result':m.result}

@app.get('/api/admin/users')
def admin_users(q:str='',u=Depends(admin),s:Session=Depends(db)):return [{'id':x.id,'login':x.login,'email':x.email,'balance':x.balance,'elo':x.elo,'role':x.role} for x in s.scalars(select(User).where(User.login.contains(q)).limit(100)).all()]
@app.post('/api/admin/users/{uid}/balance')
def admin_balance(uid:int,b:AdminBalance,u=Depends(admin),s:Session=Depends(db)):
    target=s.get(User,uid)
    if not target:raise HTTPException(404,'Игрок не найден.')
    wallet(s,target,b.amount,'Изменение баланса: '+b.comment);s.add(AdminLog(admin_id=u.id,action='balance',detail=f'{target.login}: {b.amount} ◈ — {b.comment}'));s.commit();return {'balance':target.balance}
@app.get('/api/admin/log')
def admin_log(u=Depends(admin),s:Session=Depends(db)):return [{'admin':x.admin_id,'action':x.action,'detail':x.detail,'created':x.created.isoformat()} for x in s.scalars(select(AdminLog).order_by(AdminLog.created.desc()).limit(200)).all()]
@app.get('/{path:path}')
def frontend(path:str): return FileResponse('/app/app/index.html')
