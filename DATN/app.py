from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user
from config import Config
from models import db, User
import os
import config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if not os.path.exists(db_path):
        open(db_path, "a").close()

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes import auth, customer, employee, admin, chatbot
    app.register_blueprint(auth.bp)
    app.register_blueprint(customer.bp)
    app.register_blueprint(employee.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(chatbot.bp)

    with app.app_context():
        db.create_all()

        if User.query.count() == 0:
            from seed_data import seed_database
            seed_database()
            print("Da tao du lieu mau thanh cong!")

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.role == "admin":
                return redirect(url_for("admin.dashboard"))
            elif current_user.role == "employee":
                return redirect(url_for("employee.dashboard"))
            return redirect(url_for("customer.dashboard"))
        return redirect(url_for("auth.login"))

    return app


if __name__ == "__main__":

    app = create_app()
    app.run(debug=True)
