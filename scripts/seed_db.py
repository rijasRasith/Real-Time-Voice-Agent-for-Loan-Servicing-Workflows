import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.data.models import Base, seed_database
from app.data.repository import get_engine


def main():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed_database(engine)
    print("Database successfully seeded with deterministic synthetic test data.")


if __name__ == "__main__":
    main()
