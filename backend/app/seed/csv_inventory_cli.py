from app.db.session import SessionLocal
from app.seed.csv_inventory import seed_csv_inventory


if __name__ == "__main__":
    with SessionLocal() as session:
        print(seed_csv_inventory(session))
