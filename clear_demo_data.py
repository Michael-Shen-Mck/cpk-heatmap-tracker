from seed_demo_data import clear_demo_data


if __name__ == "__main__":
    deleted_batches = clear_demo_data()
    print(f"Cleared demo batches: {deleted_batches}")
