from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import Base, engine
from .routes import router
def create_app() -> FastAPI:
   app = FastAPI(title="WS AI Builder Backend", version="0.1.0")
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   Base.metadata.create_all(bind=engine)
   app.include_router(router)
   return app
app = create_app()
