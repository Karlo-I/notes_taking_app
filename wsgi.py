from dotenv import load_dotenv

load_dotenv()

from app_factory import create_app  # noqa: E402 -- must follow load_dotenv()

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
