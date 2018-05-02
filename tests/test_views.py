from flask_fossen.testcases import FlaskTestCase

from .test_app.app import create_app, db
from .test_app.app.database import User, Article


class ViewTest(FlaskTestCase):
    app = create_app()
    db = db

    def setUp(self):
        self.session = self.db.session
        self.admin = User(name='admin', email='admin@fossen.cn')
        self.session.add(self.admin)
        self.session.commit()
        self.articles = [Article(title='article:%d'%i, content='test article:%d'%i, author=self.admin) for i in range(1)]
        self.session.add_all(self.articles)
        self.session.commit()

    def test_api(self):
        rsp = self.client.get('/api/')
        self.assertEqual(rsp.status_code, 200)
        self.assertEqual(rsp.get_data(True), 'Test.')

    def test_GET_SingleSource(self):
        rsp = self.client.get('/api/articles/1')
        self.assertEqual(rsp.status_code, 200)
        self.assertEqual(rsp.get_data(True), '{"id": 1, "title": "article:0", "content": "test article:0", "author_id": 1}')

    def test_GET_SingleSource_404(self):
        rsp = self.client.get('/api/articles/10')
        self.assertEqual(rsp.status_code, 404)
        #self.assertEqual(rsp.get_data(True), '')

    def test_PUT_SingleSource(self):
        rsp = self.client.put('/api/articles/1', json={'title': 'edited title', 'content': 'edited content', 'author_id':1}, follow_redirects=True)
        edited = Article.query.filter_by(id=1).one()
        self.assertEqual(rsp.status_code, 200)
        self.assertEqual(rsp.get_json(), edited.pre_serialize())

