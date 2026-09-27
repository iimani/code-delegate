from app import db, server


def main() -> None:
    print("[boot] starting application")
    db.connect()
    server.start_server()


if __name__ == "__main__":
    main()
