import unittest
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app, Base, db, Skin, Item, User
from sqlalchemy import select

class MatchmakingTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        def override_db():
            with Session(self.engine) as session: yield session
        app.dependency_overrides[db]=override_db
        self.a=TestClient(app);self.b=TestClient(app)
        self.assertEqual(self.a.post('/api/register',json={'login':'queue_a','email':'a@example.test','password':'password-a'}).status_code,200)
        self.assertEqual(self.b.post('/api/register',json={'login':'queue_b','email':'b@example.test','password':'password-b'}).status_code,200)
        self.viewer=TestClient(app)
        self.assertEqual(self.viewer.post('/api/register',json={'login':'queue_viewer','email':'v@example.test','password':'password-v'}).status_code,200)

    def tearDown(self):
        self.a.close();self.b.close();self.viewer.close();app.dependency_overrides.clear();Base.metadata.drop_all(self.engine);self.engine.dispose()

    def test_players_pair_by_control_and_turns_are_authoritative(self):
        first=self.a.post('/api/matches?control=3%2B2').json()
        self.assertEqual(first['status'],'searching')
        second=self.b.post('/api/matches?control=3%2B2').json()
        self.assertEqual(second['status'],'paired')
        polled=self.a.get('/api/matches/queue').json()
        self.assertEqual(polled['id'],second['id'])
        # Black cannot play first; the server enforces the side-to-move.
        self.assertEqual(self.b.post(f"/api/matches/{second['id']}/move",json={'uci':'e7e5'}).status_code,403)
        self.assertEqual(self.a.post(f"/api/matches/{second['id']}/move",json={'uci':'e2e4'}).status_code,200)
        self.assertEqual(self.a.post(f"/api/matches/{second['id']}/move",json={'uci':'e7e5'}).status_code,403)
        self.assertEqual(self.b.post(f"/api/matches/{second['id']}/move",json={'uci':'e7e5'}).status_code,200)
        for client,uci in [(self.a,'g1f3'),(self.b,'b8c6'),(self.a,'f1c4'),(self.b,'g8f6')]:
            self.assertEqual(client.post(f"/api/matches/{second['id']}/move",json={'uci':uci}).status_code,200)
        dep=self.a.post(f"/api/matches/{second['id']}/dep",json={'square':'c4','target':'queen'})
        self.assertEqual(dep.status_code,200,dep.text)
        self.assertAlmostEqual(dep.json()['chance'],1/3)
        self.assertEqual(dep.json()['fen'].split()[1],'w')
        self.assertEqual(self.a.post(f"/api/matches/{second['id']}/dep",json={'square':'c4','target':'queen'}).status_code,400)
        self.assertEqual(self.a.post(f"/api/matches/{second['id']}/move",json={'uci':'d2d3'}).status_code,200)
        black_dep=self.b.post(f"/api/matches/{second['id']}/dep",json={'square':'e5','target':'knight'})
        self.assertEqual(black_dep.status_code,200)
        self.assertEqual(self.b.post(f"/api/matches/{second['id']}/dep",json={'square':'e5','target':'knight'}).status_code,400)
        self.assertEqual(self.viewer.post(f"/api/matches/{second['id']}/chat",json={'body':'Удачная партия!'}).status_code,200)
        chat=self.a.get(f"/api/matches/{second['id']}/chat").json()
        self.assertEqual(chat[-1]['role'],'зритель')
        self.assertEqual(chat[-1]['body'],'Удачная партия!')
        self.assertEqual(self.a.get('/api/admin/users').status_code,404)
        self.assertEqual(self.a.post('/api/logout').status_code,200)
        self.assertEqual(self.a.get('/api/me').status_code,401)

    def test_pawn_can_be_deped_into_a_rook_at_twenty_percent(self):
        self.a.post('/api/matches?control=3%2B2')
        match=self.b.post('/api/matches?control=3%2B2').json()
        result=self.a.post(f"/api/matches/{match['id']}/dep",json={'square':'d2','target':'rook'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertAlmostEqual(result.json()['chance'],.2)
        self.assertEqual(result.json()['fen'].split()[1],'w')
        self.assertEqual(self.a.post(f"/api/matches/{match['id']}/move",json={'uci':'e2e4'}).status_code,200)

    def test_bot_plays_server_generated_legal_moves_and_exposes_both_clocks(self):
        match=self.a.post('/api/matches/bot?control=3%2B2',json={}).json()
        state=self.a.get(f"/api/matches/{match['id']}").json()
        self.assertTrue(state['bot_game'])
        self.assertGreater(state['white_ms'],179000)
        self.assertEqual(state['black_ms'],180000)
        self.assertEqual(state['white'],'queue_a')
        self.assertEqual(state['black'],'ChessDepBot')
        moved=self.a.post(f"/api/matches/{match['id']}/move",json={'uci':'e2e4'})
        self.assertEqual(moved.status_code,200,moved.text)
        time.sleep(.9)
        state=self.a.get(f"/api/matches/{match['id']}").json()
        self.assertEqual(state['turn'],'white')
        self.assertEqual(len(state['pgn'].split()),2)
        self.assertIn('dep_white',state)
        self.assertIn('dep_black',state)

    def test_equipment_is_frozen_at_match_start_and_targets_are_exposed(self):
        with Session(self.engine) as session:
            uid=session.scalar(select(User.id).where(User.login=='queue_a'))
            skin=Skin(name='Конь | Лазурь',kind='figure',piece='knight',rarity='редкий',value=150,color='#38e8ff',target=True)
            session.add(skin);session.flush()
            item=Item(user_id=uid,skin_id=skin.id,wear=.1,equipped=True)
            session.add(item);session.commit();item_id=item.id
        self.assertTrue(self.a.get('/api/skins').json()[0]['target'])
        match=self.a.post('/api/matches/bot?control=3%2B2').json()
        self.assertEqual(self.a.post('/api/unequip',json={'id':item_id}).status_code,200)
        state=self.a.get(f"/api/matches/{match['id']}").json()
        self.assertEqual(state['equipment']['white']['knight']['color'],'#38e8ff')

if __name__=='__main__':unittest.main()
