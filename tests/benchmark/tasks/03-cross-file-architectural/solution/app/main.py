from app.container import build_container


def main(logger=None) -> None:
    c = build_container(logger)
    c.logger.info("[boot] starting application")
    c.db.connect()
    c.server.start()


if __name__ == "__main__":
    main()
