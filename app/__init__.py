from flask import Flask
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Đăng ký Blueprints
    from app.routes.customer import customer_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(customer_bp)
    app.register_blueprint(admin_bp)

    return app
