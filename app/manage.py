"""Container administration commands: python -m app.manage promote LOGIN"""
import sys
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.main import engine, User

def main():
    if len(sys.argv)!=3 or sys.argv[1]!='promote':
        print('Использование: python -m app.manage promote LOGIN');raise SystemExit(2)
    with Session(engine) as s:
        u=s.scalar(select(User).where(User.login==sys.argv[2]))
        if not u:print('Пользователь не найден.');raise SystemExit(1)
        u.role='admin';s.commit();print(f'{u.login}: роль администратора назначена.')
if __name__=='__main__':main()
