import unittest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.main import Base, User, Ledger, wallet

class WalletTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session=Session(self.engine)
        self.user=User(login='wallet_test',email='wallet@example.test',password='hash',balance=10,elo=1200)
        self.session.add(self.user);self.session.commit()

    def tearDown(self):
        self.session.close();Base.metadata.drop_all(self.engine);self.engine.dispose()

    def test_wallet_records_credit_and_debit(self):
        wallet(self.session,self.user,-7,'Тест покупки');self.session.commit()
        self.assertEqual(self.user.balance,3)
        self.assertEqual(self.session.scalar(select(func.sum(Ledger.amount)).where(Ledger.user_id==self.user.id)),-7)

    def test_wallet_rejects_negative_balance_without_ledger_entry(self):
        with self.assertRaises(HTTPException):wallet(self.session,self.user,-11,'Недопустимо')
        self.session.rollback()
        self.assertEqual(self.user.balance,10)
        self.assertEqual(self.session.scalar(select(func.count(Ledger.id))),0)

if __name__=='__main__':unittest.main()
