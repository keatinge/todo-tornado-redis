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

        if self.redis.closed:
            await self.redis_init()


        max_id_str = await self.redis.get("max_id") or b"0"
        max_id = int(max_id_str.decode("utf-8"))
        this_id = max_id + 1
        full_todo_data = {
            "title": todo["title"],
            "completed": str(todo["completed"]).lower(),
            "id" : this_id
        }
        incr_future = self.redis.incr("max_id")
        hmset_future = self.redis.hmset_dict(f"todo:{this_id}", full_todo_data)
        sadd_future = self.redis.sadd("todo_ids", this_id)

        await tornado.gen.multi([incr_future, hmset_future, sadd_future])


    async def delete_todo(self, todo_id):

        if self.redis.closed:
            await self.redis_init()


        key_del_future = self.redis.delete(f"todo:{todo_id}")
        srem_future = self.redis.srem("todo_ids", todo_id)

        await tornado.gen.multi([key_del_future, srem_future])


    async def update_checked(self, todo_id, is_checked):

        if self.redis.closed:
            await self.redis_init()

        await self.redis.hset(f"todo:{todo_id}", "completed", is_checked)



    @staticmethod
    def map_to_todo(dict_from_redis):

        print(dict_from_redis)
        return {
            "id" : dict_from_redis[b"id"].decode("utf-8"),
            "completed" : dict_from_redis[b"completed"].decode("utf-8") == "true",
            "title" : dict_from_redis[b"title"].decode("utf-8"),
        }


    async def get_todos(self):


        if self.redis.closed:
            await self.redis_init()

        members = await self.redis.smembers("todo_ids")
        awaitables = [self.redis.hgetall("todo:" + memb.decode("utf-8")) for memb in members]

        if awaitables:
            done, pending = await asyncio.wait(awaitables)
        else:
            done = []
        results = [RedisStore.map_to_todo(r.result()) for r in done]

        return results








class TodoWebSocket(tornado.websocket.WebSocketHandler):
    redis_store = RedisStore()
    open_cons = set()

    async def on_message(self, message):
        message_data = json.loads(message)
        message_type = message_data["message_type"]
        if message_type == "get_todos":
            pass
        elif message_type == "add_todo":
            await self.redis_store.add_todo(message_data["new_todo"])
        elif message_type == "del_todo":
            await self.redis_store.delete_todo(message_data["todo_id"])
        elif message_type == "set_checked_state":
            print(str(message_data["is_checked"]).lower())
            await self.redis_store.update_checked(message_data["todo_id"], str(message_data["is_checked"]).lower())

        await self.update_all_clients()

    async def send_todos_update(self):
        message = {
            "message_type" : "todos_update",
            "todos": await self.redis_store.get_todos()
        }

        try:
            await self.write_message(json.dumps(message))
        except tornado.websocket.WebSocketClosedError:
            pass

    async def update_all_clients(self):
        active = list(self.open_cons)
        futures = [client.send_todos_update() for client in active]
        await tornado.gen.multi(futures)




    def open(self):
        self.open_cons.add(self)
        print(len(self.open_cons), "current connections")


    def on_close(self):
        self.open_cons.remove(self)
        print(len(self.open_cons), "current connections")


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