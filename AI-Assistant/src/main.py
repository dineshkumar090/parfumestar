# # from fastapi import FastAPI
# # from fastapi.middleware.cors import CORSMiddleware
# # from fastapi.staticfiles import StaticFiles
# # from fastapi.responses import FileResponse
# # import os

# # from app.api.auth import router as auth_router
# # from app.routes import admin
# # from app.api import webhooks
# # from app.api.admin import chatbot
# # from app.database import engine, Base

# # app = FastAPI()

# # # ---------------------------
# # # Routers
# # # ---------------------------
# # app.include_router(auth_router)
# # app.include_router(admin.router, prefix="/api")
# # app.include_router(webhooks.router)
# # app.include_router(chatbot.router)

# # # ---------------------------
# # # Serve Frontend (IMPORTANT 🔥)
# # # ---------------------------
# # BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# # FRONTEND_DIR = r"D:\machine_learning\RAG\April\new\AI-Assistant\build"
# # # FRONTEND_DIR = os.path.join(BASE_DIR, "AI-Assistant", "build")

# # # Static assets
# # app.mount(
# #     "/assets",
# #     StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")),
# #     name="assets"
# # )

# # # ---------------------------
# # # 🆕 Serve Chatbot Widget
# # # ---------------------------
# # # Method 1: If widget is in build folder
# # @app.get("/chatbot-widget.js")
# # async def serve_widget():
# #     widget_path = os.path.join(FRONTEND_DIR, "chatbot-widget.js")
# #     if os.path.exists(widget_path):
# #         return FileResponse(widget_path, media_type="application/javascript")
    
# #     # Method 2: If widget is in public folder (before build)
# #     public_widget = os.path.join(os.path.dirname(FRONTEND_DIR), "public", "chatbot-widget.js")
# #     if os.path.exists(public_widget):
# #         return FileResponse(public_widget, media_type="application/javascript")
    
# #     return {"error": "Widget not found"}

# # # Optional: Serve widget from static folder
# # os.makedirs("static", exist_ok=True)
# # app.mount("/static", StaticFiles(directory="static"), name="static")

# # # Root route
# # @app.get("/")
# # def serve_frontend():
# #     index_path = os.path.join(FRONTEND_DIR, "index.html")
# #     if os.path.exists(index_path):
# #         return FileResponse(index_path)
# #     return {"error": "Frontend not built properly"}

# # # Test route for widget
# # @app.get("/widget-test")
# # def widget_test():
# #     return {"message": "Widget endpoint is working!"}

# # # ---------------------------
# # # Test Route
# # # ---------------------------
# # @app.get("/message")
# # def read_root():
# #     return {"message": "Welcome to the Shopify AI Assistant!"}

# # # ---------------------------
# # # Database
# # # ---------------------------
# # @app.on_event("startup")
# # def create_tables():
# #     Base.metadata.create_all(bind=engine)

# # # ---------------------------
# # # CORS (UPDATED)
# # # ---------------------------
# # origins = [
# #     # "http://localhost:5173",
# #     # "http://127.0.0.1:5173",
# #     # "https://8tth2g1z-8001.inc1.devtunnels.ms",
# #     # "https://8tth2g1z-5173.inc1.devtunnels.ms",
# #     "https://my-teststo.myshopify.com",  # Add your Shopify store
# #     "*"  # For testing (remove in production)
# # ]

# # app.add_middleware(
# #     CORSMiddleware,
# #     allow_origins=origins,
# #     allow_credentials=True,
# #     allow_methods=["*"],
# #     allow_headers=["*"],
# # )

# # ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

# # from fastapi import FastAPI
# # from fastapi.middleware.cors import CORSMiddleware
# # from fastapi.staticfiles import StaticFiles
# # from fastapi.responses import FileResponse
# # import os


# # from app.models.chat import ChatThread, ChatMessage

# # from app.api.auth import router as auth_router
# # from app.routes import admin
# # from app.api import webhooks
# # from app.api.admin import chatbot          # existing chatbot (ai-search, sync, etc.)
# # from app.api.admin.chatbot import router as chat_router   # ← NEW chat threads router
# # from app.database import engine, Base

# # app = FastAPI()

# # # ---------------------------
# # # Routers
# # # ---------------------------
# # app.include_router(auth_router)
# # app.include_router(admin.router, prefix="/api")
# # app.include_router(webhooks.router)
# # app.include_router(chatbot.router, prefix="/api")

# """
# main.py  —  add these two lines to register the new chat router.
# Nothing else in main.py needs to change.
 
# ────────────────────────────────────────────────────────────────
# STEP 1 – add the import near the top of main.py:
# ────────────────────────────────────────────────────────────────
 
#     from app.api.chat_routes import router as chat_router
 
# ────────────────────────────────────────────────────────────────
# STEP 2 – register the router (alongside your existing routers):
# ────────────────────────────────────────────────────────────────
 
#     app.include_router(chat_router)
 
# ────────────────────────────────────────────────────────────────
# STEP 3 – make sure the new models are imported so SQLAlchemy
#          creates the tables on startup:
# ────────────────────────────────────────────────────────────────
 
#     from app.models import chat  # noqa – registers ChatThread / ChatMessage
 
# ────────────────────────────────────────────────────────────────
# Full relevant section of main.py for reference:
# ────────────────────────────────────────────────────────────────
# """
 
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from fastapi.responses import FileResponse
# import os
 
# from app.api.auth import router as auth_router
# from app.routes import admin
# from app.api import webhooks
# # from app.api.admin import chatbot
# from app.database import engine, Base
 
# # ── NEW IMPORT ──────────────────────────────────────────────────────────────
# from app.api.chat_routes import router as chat_router   # ← add this
# from app.models import chat as _chat_models             # ← ensures tables are created
# # ───────────────────────────────────────────────────────────────────────────
 
# app = FastAPI()
 
# # ── Routers ─────────────────────────────────────────────────────────────────
# app.include_router(auth_router)
# app.include_router(admin.router, prefix="/api")
# app.include_router(webhooks.router)
# # app.include_router(chatbot.router)
# app.include_router(chat_router)   


# # ---------------------------
# # Serve Frontend
# # ---------------------------
# BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# FRONTEND_DIR = r"D:\machine_learning\RAG\April\new\AI-Assistant\build"

# app.mount(
#     "/assets",
#     StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")),
#     name="assets"
# )

# # ---------------------------
# # Serve Chatbot Widget
# # ---------------------------
# @app.get("/chatbot-widget.js")
# async def serve_widget():
#     widget_path = os.path.join(FRONTEND_DIR, "chatbot-widget.js")
#     if os.path.exists(widget_path):
#         return FileResponse(widget_path, media_type="application/javascript")

#     public_widget = os.path.join(os.path.dirname(FRONTEND_DIR), "public", "chatbot-widget.js")
#     if os.path.exists(public_widget):
#         return FileResponse(public_widget, media_type="application/javascript")

#     return {"error": "Widget not found"}

# os.makedirs("static", exist_ok=True)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# @app.get("/")
# def serve_frontend():
#     index_path = os.path.join(FRONTEND_DIR, "index.html")
#     if os.path.exists(index_path):
#         return FileResponse(index_path)
#     return {"error": "Frontend not built properly"}

# @app.get("/widget-test")
# def widget_test():
#     return {"message": "Widget endpoint is working!"}

# @app.get("/message")
# def read_root():
#     return {"message": "Welcome to the Shopify AI Assistant!"}

# # ---------------------------
# # Database — auto-create all tables on startup
# # ---------------------------
# @app.on_event("startup")
# def create_tables():
#     # Import all models so SQLAlchemy knows about them before create_all
#     from app.models import products, store, sync_log, chat, chatbot_config  # noqa: F401
#     Base.metadata.create_all(bind=engine)

# # ---------------------------
# # CORS
# # ---------------------------
# origins = [
#     "https://modernalchemyformulas.com",  # remove in production
#     "*"  # remove in production
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from fastapi import Request
from fastapi.responses import RedirectResponse

from app.api.auth import router as auth_router
from app.routes import admin
from app.api import webhooks
from app.database import engine, Base
 
from app.api.chat_routes      import router as chat_router
from app.api.analytics_routes import router as analytics_router   # ← NEW
from app.models import chat as _chat_models
from app.models import sync_log as _sync_log_models               # ← NEW
 
from app.models.chat import EngagementEvent   # noqa – registers table
 
 
app = FastAPI()
 
app.include_router(auth_router)
app.include_router(admin.router, prefix="/api")
app.include_router(webhooks.router)
app.include_router(chat_router)
app.include_router(analytics_router) 


@app.get("/")
async def root(request: Request):
    """
    Root endpoint - handles Shopify installation redirects
    """
    shop = request.query_params.get("shop")
    host = request.query_params.get("host")
    hmac = request.query_params.get("hmac")
    timestamp = request.query_params.get("timestamp")
    
    # If this is a Shopify installation request, redirect to auth
    if shop and hmac:
        redirect_url = f"/auth?shop={shop}&host={host}&hmac={hmac}&timestamp={timestamp}"
        print(f"Redirecting to: {redirect_url}")
        return RedirectResponse(redirect_url)
    
    return {
        "message": "Shopify AI Assistant App is running",
        "status": "active",
        "endpoints": {
            "auth": "/auth",
            "auth_callback": "/auth/callback/",
            "uninstall": "/uninstall"
        }
    }

# ---------------------------
# Serve Frontend
# ---------------------------
# ---------------------------
# Serve Frontend (Dynamic)
# ---------------------------
# BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# # Try multiple possible locations
# FRONTEND_DIR = os.path.join(BASE_DIR, "AI-Assistant", "build")

# if not os.path.exists(FRONTEND_DIR):
#     FRONTEND_DIR = os.path.join(BASE_DIR, "AI-Assistant", "dist")

# # Mount assets only if exists
# assets_path = os.path.join(FRONTEND_DIR, "assets")
# if os.path.exists(assets_path):
#     app.mount("/assets", StaticFiles(directory=assets_path), name="assets")


# ---------------------------
# Serve Chatbot Widget
# ---------------------------
@app.get("/chatbot-widget.js")
async def serve_widget():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    widget_path = os.path.join(
        base_dir,
        "..",   # app → chatbot
        "AI-Assistant",
        "public",
        "chatbot-widget.js"
    )

    widget_path = os.path.abspath(widget_path)

    print("Resolved widget path:", widget_path)

    if os.path.exists(widget_path):
        return FileResponse(widget_path, media_type="application/javascript")

    return {"error": f"Widget not found at {widget_path}"}
async def serve_widget():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    widget_path = os.path.join(
        base_dir,
        "..",                  # app → chatbot
        "AI-Assistant",
        "public",
        "chatbot-widget.js"
    )

    widget_path = os.path.abspath(widget_path)

    print("Resolved widget path:", widget_path)

    if os.path.exists(widget_path):
        return FileResponse(widget_path, media_type="application/javascript")

    return {"error": f"Widget not found at {widget_path}"}@app.get("/chatbot-widget.js")
async def serve_widget():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    widget_path = os.path.join(
        base_dir,
        "..",                  # app → chatbot
        "AI-Assistant",
        "public",
        "chatbot-widget.js"
    )

    widget_path = os.path.abspath(widget_path)

    print("Resolved widget path:", widget_path)

    if os.path.exists(widget_path):
        return FileResponse(widget_path, media_type="application/javascript")

    return {"error": f"Widget not found at {widget_path}"}

# os.makedirs("static", exist_ok=True)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# @app.get("/{full_path:path}")
# def serve_react_app(full_path: str):
#     index_path = os.path.join(FRONTEND_DIR, "index.html")
#     if os.path.exists(index_path):
#         return FileResponse(index_path)
#     return {"error": "Frontend not built"}

@app.get("/widget-test")
def widget_test():
    return {"message": "Widget endpoint is working!"}

@app.get("/message")
def read_root():
    return {"message": "Welcome to the Shopify AI Assistant!"}

# ---------------------------
# Database — auto-create all tables on startup
# ---------------------------
@app.on_event("startup")
def create_tables():
    # Import all models so SQLAlchemy knows about them before create_all
    from app.models import products, store, sync_log, chat, chatbot_config  # noqa: F401
    Base.metadata.create_all(bind=engine)

# ---------------------------
# CORS
# ---------------------------
origins = [
  "*"  # remove in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
