import tornado.ioloop
import tornado.web
import tornado.websocket
import aioredis
import json
import asyncio

async def get_response_body(url):
    client = tornado.httpclient.AsyncHTTPClient()
    response = await client.fetch(url)
    response_text = response.body.decode("utf-8")
    return response_text


class RedisStore:
    DATABASE_INDEX = 1


    def __init__(self):
        self.init_fut = self.redis_init()

    async def redis_init(self):
        self.redis = await aioredis.create_redis('redis://localhost', loop=tornado.ioloop.IOLoop.current().asyncio_loop)
        await self.redis.select(self.DATABASE_INDEX)

        print("REDIS SETUP")

        # setup initial max_id


    async def add_todo(self, todo):

        max_id = await self.redis.get("max_id") or 0
        this_id = max_id + 1
        full_todo_data = {**todo, "id" : this_id}
        await self.redis.hmset_dict(f"todo:{this_id}", full_todo_data)
        await self.redis.sadd("todo_ids", this_id)

    @staticmethod
    def map_to_todo(dict_from_redis):

        print(dict_from_redis)
        return {
            "id" : dict_from_redis[b"id"].decode("utf-8"),
            "completed" : dict_from_redis[b"completed"].decode("utf-8") == "true",
            "title" : dict_from_redis[b"title"].decode("utf-8"),
        }


    async def get_todos(self):
        members = await self.redis.smembers("todo_ids")
        awaitables = [self.redis.hgetall("todo:" + memb.decode("utf-8")) for memb in members]

        done, pending = await asyncio.wait(awaitables)
        results = [RedisStore.map_to_todo(r.result()) for r in done]

        print(results)
        return results








class TodoWebSocket(tornado.websocket.WebSocketHandler):
    redis_store = RedisStore()
    def __init__(self, *args, **kwargs):
        super(TodoWebSocket, self).__init__(*args, **kwargs)


    async def on_message(self, message):
        if message == "get_todos":
            await self.send_todos_update()


    async def send_todos_update(self):
        message = {
            "message_type" : "todos_update",
            "todos": await self.redis_store.get_todos()
        }

        await self.write_message(json.dumps(message))



class HomePage(tornado.web.RequestHandler):
    def get(self):
        with open("tornado_homepage.html") as f:
            html_str = f.read()
        self.write(html_str)

def main():

    tornado.ioloop.IOLoop.current().asyncio_loop.run_until_complete(TodoWebSocket.redis_store.redis_init())
    app = tornado.web.Application([
        (r"/ws", TodoWebSocket),
        (r"/", HomePage)
    ])

    app.listen(8888)


    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()