from __future__ import annotations
import os, secrets, hashlib, hmac, time, json, random
from datetime import datetime, timezone, timedelta
from typing import Optional
import chess
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

DB_URL=os.getenv('DATABASE_URL','sqlite:///./chessdep.db')
engine=create_engine(DB_URL,connect_args={'check_same_thread':False} if DB_URL.startswith('sqlite') else {},pool_pre_ping=True)
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id:Mapped[int]=mapped_column(primary_key=True); login:Mapped[str]=mapped_column(String(16),unique=True,index=True); email:Mapped[str]=mapped_column(String(254),unique=True,index=True); password:Mapped[str]=mapped_column(String(255)); role:Mapped[str]=mapped_column(String(12),default='player'); balance:Mapped[int]=mapped_column(Integer,default=1000); elo:Mapped[int]=mapped_column(Integer,default=1200); joined:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc)); last_daily:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
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
    id:Mapped[int]=mapped_column(primary_key=True); white_id:Mapped[int]=mapped_column(ForeignKey('users.id')); black_id:Mapped[int]=mapped_column(ForeignKey('users.id')); control:Mapped[str]=mapped_column(String(8)); fen:Mapped[str]=mapped_column(Text); pgn:Mapped[str]=mapped_column(Text,default=''); status:Mapped[str]=mapped_column(String(12),default='active'); result:Mapped[str]=mapped_column(String(30),default=''); dep_white:Mapped[int]=mapped_column(Integer,default=0); dep_black:Mapped[int]=mapped_column(Integer,default=0); dep_used:Mapped[bool]=mapped_column(Boolean,default=False); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class AdminLog(Base):
    __tablename__='admin_log'
    id:Mapped[int]=mapped_column(primary_key=True); admin_id:Mapped[int]=mapped_column(Integer); action:Mapped[str]=mapped_column(String(120)); detail:Mapped[str]=mapped_column(Text); created:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
Base.metadata.create_all(engine)
ph=PasswordHasher(); app=FastAPI(title='ChessDep')
app.mount('/static',StaticFiles(directory='/app/app/static'),name='static')
RARITIES=[('Обычный','обычный','#9aa4b2',20),('Необычный','необычный','#38e8ff',60),('Редкий','редкий','#8b5cf6',150),('Эпический','эпический','#ffc93c',500),('Легендарный','легендарный','#ff7847',1500),('Мифический','мифический','#ff5470',5000)]
PIECES=[('Пешка','pawn','♙'),('Конь','knight','♘'),('Слон','bishop','♗'),('Ладья','rook','♖'),('Ферзь','queen','♕'),('Король','king','♔')]
def db():
    with Session(engine) as s: yield s
def token(user_id:int):
    raw=f'{user_id}:{int(time.time())+86400}'; sig=hmac.new(os.getenv('SESSION_SECRET','dev-secret').encode(),raw.encode(),hashlib.sha256).hexdigest(); return raw+'.'+sig
def current(request:Request,s:Session=Depends(db)):
    t=request.cookies.get('session','')
    try:
        raw,sig=t.rsplit('.',1); uid,exp=raw.split(':'); good=hmac.compare_digest(sig,hmac.new(os.getenv('SESSION_SECRET','dev-secret').encode(),raw.encode(),hashlib.sha256).hexdigest()) and int(exp)>time.time()
    except Exception: good=False
    u=s.get(User,int(uid)) if good else None
    if not u: raise HTTPException(401,'Войдите в аккаунт.')
    return u
def admin(u=Depends(current)):
    if u.role!='admin': raise HTTPException(404,'Страница не найдена.')
    return u
def wallet(s,u,amount,label):
    if u.balance+amount<0: raise HTTPException(400,'Недостаточно кристаллов.')
    u.balance+=amount;s.add(Ledger(user_id=u.id,amount=amount,label=label))
def skin_json(skin): return {'id':skin.id,'name':skin.name,'kind':skin.kind,'piece':skin.piece,'rarity':skin.rarity,'value':skin.value,'color':skin.color,'light':skin.light,'dark':skin.dark,'collection':skin.collection}
def item_json(s,it):
    sk=s.get(Skin,it.skin_id); return {'id':it.id,'wear':it.wear,'equipped':it.equipped,'skin':skin_json(sk)}
def seed():
  with Session(engine) as s:
    if s.scalar(select(func.count(Skin.id)))==0:
      for label,slug,color,value in RARITIES:
        for pname,piece,glyph in PIECES:
          s.add(Skin(name=f'{pname} | {label}',kind='figure',piece=piece,rarity=slug,value=value,color='#f5f5f5',target=True))
      for name,rarity in [('Бумага','обычный'),('Фарфор','необычный'),('Мрамор','эпический'),('Альбион','мифический')]:
        r=next(x for x in RARITIES if x[1]==rarity);s.add(Skin(name=name,kind='board',piece='board',rarity=rarity,value=r[3],light='#454f77',dark='#262e4d',target=True))
      s.add_all([Case(name='Genesis: фигуры',price=100,kind='figure'),Case(name='Genesis: доски',price=250,kind='board')]);s.commit()
seed()
class Credentials(BaseModel): login:str; email:str=''; password:str
class IdBody(BaseModel): id:int
class PriceBody(BaseModel): item_id:int; price:int=Field(ge=1,le=10000000)
class GiftBody(BaseModel): item_id:int; login:str; note:str=Field(default='',max_length=140)
class MoveBody(BaseModel): uci:str
class DepBody(BaseModel): square:str; target:str
class UpgradeBody(BaseModel): item_ids:list[int]=Field(min_length=1,max_length=10); target_skin:int
class AdminBalance(BaseModel): amount:int; comment:str=Field(min_length=3,max_length=200)

@app.post('/api/register')
def register(b:Credentials,response:Response,s:Session=Depends(db)):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,16}',b.login): raise HTTPException(400,'Логин: 3–16 символов, латиница, цифры, _ или -.')
    if '@' not in b.email or len(b.password)<8: raise HTTPException(400,'Проверьте email и пароль (не менее 8 символов).')
    if s.scalar(select(User).where((User.login==b.login)|(User.email==b.email))): raise HTTPException(409,'Логин или email уже зарегистрирован.')
    u=User(login=b.login,email=b.email,password=ph.hash(b.password));u.role='admin' if b.email and b.email==os.getenv('ADMIN_EMAIL') else 'player';s.add(u);s.flush();s.add(Ledger(user_id=u.id,amount=1000,label='Бонус за регистрацию'));s.commit();response.set_cookie('session',token(u.id),httponly=True,samesite='lax',secure=False,max_age=86400);return {'ok':True}
@app.post('/api/login')
def login(b:Credentials,response:Response,s:Session=Depends(db)):
    u=s.scalar(select(User).where(User.login==b.login))
    try: valid=u and ph.verify(u.password,b.password)
    except VerifyMismatchError: valid=False
    if not valid: raise HTTPException(401,'Неверный логин или пароль.')
    response.set_cookie('session',token(u.id),httponly=True,samesite='lax',secure=False,max_age=86400);return {'ok':True}
@app.post('/api/logout')
def logout(response:Response): response.delete_cookie('session');return {'ok':True}
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
@app.post('/api/cases/{case_id}/open')
def open_case(case_id:int,u=Depends(current),s:Session=Depends(db)):
    c=s.get(Case,case_id)
    if not c:raise HTTPException(404,'Кейс не найден.')
    wallet(s,u,-c.price,f'Покупка кейса: {c.name}')
    pool=s.scalars(select(Skin).where(Skin.kind==c.kind)).all()
    # Higher rarity has lower probability; server CSPRNG chooses outcome.
    weights=[max(1,1000//max(1,sk.value)) for sk in pool]; sk=secrets.SystemRandom().choices(pool,weights=weights,k=1)[0]
    wear=secrets.randbelow(1000001)/1000000;it=Item(user_id=u.id,skin_id=sk.id,wear=wear);s.add(it);s.commit();return {'item':item_json(s,it),'balance':u.balance}
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
    it.user_id=recipient.id;it.equipped=False;s.add(Gift(item_id=it.id,sender_id=u.id,recipient_id=recipient.id,note=b.note));s.commit();return {'ok':True}
@app.get('/api/gifts')
def gifts(u=Depends(current),s:Session=Depends(db)):
    rows=s.scalars(select(Gift).where((Gift.recipient_id==u.id)|(Gift.sender_id==u.id)).order_by(Gift.created.desc())).all();out=[]
    for g in rows:
      g.seen=True;out.append({'from':s.get(User,g.sender_id).login,'to':s.get(User,g.recipient_id).login,'note':g.note,'item':item_json(s,s.get(Item,g.item_id)),'seen':g.seen})
    s.commit();return out
@app.get('/api/skins')
def skins(s:Session=Depends(db)):return [skin_json(k) for k in s.scalars(select(Skin)).all()]
@app.get('/api/leaderboard')
def leaderboard(sort:str='elo',s:Session=Depends(db)):
    col=User.balance if sort=='balance' else User.elo
    return [{'place':i+1,'login':u.login,'elo':u.elo,'balance':u.balance} for i,u in enumerate(s.scalars(select(User).order_by(col.desc()).limit(100)).all())]
@app.get('/api/ledger')
def ledger(u=Depends(current),s:Session=Depends(db)):return [{'amount':x.amount,'label':x.label,'created':x.created.isoformat()} for x in s.scalars(select(Ledger).where(Ledger.user_id==u.id).order_by(Ledger.created.desc()).limit(100)).all()]
@app.post('/api/upgrade')
def upgrade(b:UpgradeBody,u=Depends(current),s:Session=Depends(db)):
    its=[s.get(Item,i) for i in set(b.item_ids)]
    if len(its)!=len(b.item_ids) or any(not i or i.user_id!=u.id for i in its):raise HTTPException(400,'Выберите только свои предметы.')
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
    # Solo training match provides a playable board; matchmaking can pair two sessions later.
    m=Match(white_id=u.id,black_id=u.id,control=control,fen=chess.STARTING_FEN,pgn='');s.add(m);s.commit();return {'id':m.id,'fen':m.fen,'status':m.status}
@app.get('/api/matches/{mid}')
def match_state(mid:int,u=Depends(current),s:Session=Depends(db)):
    m=s.get(Match,mid)
    if not m:raise HTTPException(404,'Партия не найдена.')
    board=chess.Board(m.fen);return {'id':m.id,'fen':m.fen,'status':m.status,'result':m.result,'turn':'white' if board.turn else 'black','check':board.is_check(),'legal':[x.uci() for x in board.legal_moves],'pgn':m.pgn}
@app.post('/api/matches/{mid}/move')
def move(mid:int,b:MoveBody,u=Depends(current),s:Session=Depends(db)):
    m=s.get(Match,mid)
    if not m or m.status!='active':raise HTTPException(404,'Активная партия не найдена.')
    if m.white_id!=u.id and m.black_id!=u.id:raise HTTPException(403,'Вы не участник партии.')
    board=chess.Board(m.fen)
    if b.uci not in [x.uci() for x in board.legal_moves]:raise HTTPException(400,'Недопустимый ход.')
    board.push_uci(b.uci);m.fen=board.fen();m.pgn=(m.pgn+' '+b.uci).strip();m.dep_used=False
    if board.is_checkmate() or board.is_stalemate() or board.is_insufficient_material() or board.can_claim_threefold_repetition() or board.can_claim_fifty_moves():m.status='finished';m.result='Мат' if board.is_checkmate() else 'Ничья'
    s.commit();return {'fen':m.fen,'status':m.status,'result':m.result}
@app.post('/api/matches/{mid}/dep')
def dep(mid:int,b:DepBody,u=Depends(current),s:Session=Depends(db)):
    m=s.get(Match,mid)
    if not m or m.status!='active':raise HTTPException(404,'Активная партия не найдена.')
    if u.id not in (m.white_id,m.black_id):raise HTTPException(403,'Вы не участник партии.')
    board=chess.Board(m.fen); color=board.turn
    count=m.dep_white if color else m.dep_black
    if m.dep_used:raise HTTPException(400,'За этот ход деп уже использован.')
    if count>=10:raise HTTPException(400,'Достигнут лимит депов за партию.')
    try: square=chess.parse_square(b.square); target={'knight':chess.KNIGHT,'bishop':chess.BISHOP,'rook':chess.ROOK,'queen':chess.QUEEN}[b.target]
    except Exception:raise HTTPException(400,'Неверная фигура или цель депа.')
    piece=board.piece_at(square)
    if not piece or piece.color!=color or piece.piece_type==chess.KING:raise HTTPException(400,'Выберите свою фигуру, кроме короля.')
    values={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9}
    if piece.piece_type==chess.QUEEN or values[piece.piece_type]>=values[target]:raise HTTPException(400,'Нет цели большей ценности.')
    # Neither possible result may give check to the opponent.
    outcomes=[]
    for success in (False,True):
      candidate=board.copy();candidate.remove_piece_at(square)
      if success:candidate.set_piece_at(square,chess.Piece(target,color))
      candidate.turn=not color
      outcomes.append(candidate)
    if any(candidate.is_check() for candidate in outcomes):raise HTTPException(400,'Даст шах сопернику.')
    chance=values[piece.piece_type]/values[target];won=secrets.randbelow(1000000)<int(chance*1000000)
    board.remove_piece_at(square)
    if won:board.set_piece_at(square,chess.Piece(target,color))
    # A dep consumes the turn and updates the repetition/halfmove state.
    board.push(chess.Move.null());m.fen=board.fen();m.dep_used=True
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
