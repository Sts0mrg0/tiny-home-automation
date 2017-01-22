import asyncio
import json
import logging
import os

from aiohttp import web

BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LOG = logging.getLogger(__name__)


class WebSocket(web.View):
    @asyncio.coroutine
    def get(self):
        ws = web.WebSocketResponse()
        yield from ws.prepare(self.request)
        LOG.info('ws client connected, %s clients', len(self.request.app['websockets']) + 1)
        self.request.app['websockets'].append(ws)

        try:
            while 1:
                msg = yield from ws.receive_str()
                name, cmd = msg.split(';')
                self.request.app.context.command(name, cmd)
                LOG.debug('ws msg: %s', msg)
                yield from asyncio.sleep(0.01)
        finally:
            if not ws.closed:
                try:
                    ws.close()
                except:
                    pass
            self.request.app['websockets'].remove(ws)
            LOG.debug('websocket connection closed')
        return ws


class Server(web.Application):
    context = None

    def init(self):
        self['websockets'] = []
        self.router.add_static('/static/', os.path.join(BASE_PATH, 'static'), name='static')
        self.router.add_route('GET', '/ws', WebSocket, name='chat')
        self.router.add_route('GET', '/', self.index)
        self.router.add_route('GET', '/2', self.index2)
        self.router.add_route('GET', '/items/', self.get_items)
        self.router.add_route('GET', '/items/{tag}', self.get_items)
        self.router.add_route('GET', '/item/{name}', self.get_item)
        self.router.add_route('GET', '/item/{name}/', self.get_item)
        self.router.add_route('PUT', '/item/{name}', self.put_item)
        self.router.add_route('PUT', '/item/{name}/', self.put_item)
        self.router.add_route('POST', '/item/{name}', self.post_item)
        self.router.add_route('POST', '/item/{name}/', self.post_item)

    def get_app(self, config, loop):
        LOG.info('server on port %s', config['server']['port'])
        return loop.create_server(self.make_handler(), host='0.0.0.0', port=config['server']['port'])

    def json_resp(self, s):
        headers = {'content-type': 'application/json'}
        return web.Response(body=json.dumps(s).encode('UTF-8'), headers=headers)

    def resp_404(self, s):
        return web.Response(body=s.encode('UTF-8'), status=404)

    @asyncio.coroutine
    def index(self, request):
        return web.Response(body=open('static/index.html').read().encode('UTF-8'), content_type='text/html')

    @asyncio.coroutine
    def index2(self, request):
        return web.Response(body=open('static/index2.html').read().encode('UTF-8'), content_type='text/html')

    @asyncio.coroutine
    def get_items(self, request):
        tag = request.match_info.get('tag')
        return self.json_resp(self.context.items.as_list(tag))

    @asyncio.coroutine
    def get_item(self, request):
        name = request.match_info['name']
        item = self.context.items.get_item(name)
        if not item:
            return self.resp_404('item %s not found' % name)
        return self.json_resp(item.to_dict())

    @asyncio.coroutine
    def put_item(self, request):
        name = request.match_info['name']
        item = self.context.items.get_item(name)
        if not item:
            return self.resp_404('')
        val = yield from request.payload.read()
        self.context.set_item_value(name, val.decode('utf-8'))
        return self.json_resp(item.to_dict())

    @asyncio.coroutine
    def post_item(self, request):
        name = request.match_info['name']
        item = self.context.items.get_item(name)
        if not item:
            return self.resp_404('')
        val = yield from request.content.read()
        self.context.command(name, val.decode('utf-8'))
        return self.json_resp(item.to_dict())

    @asyncio.coroutine
    def on_change(self, s):
        for ws in self['websockets']:
            try:
                yield from ws.send_str(s)
            except:
                pass


def get_app(context, config, loop):
    s = Server()
    s.context = context
    s.init()
    context.listeners.append(s.on_change)
    return s.get_app(config, loop)
