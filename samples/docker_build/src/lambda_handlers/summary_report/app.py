import pandas as pd
import os


def lambda_handler(event: dict, context) -> dict:
    """
    Lambda function to return a response to the client
    """

    directory = os.path.dirname(os.path.realpath(__file__))
    file_path = os.path.join(directory, "mock-data", "usage.csv")
    df: pd.DataFrame = pd.read_csv(file_path)

    filter = event.get("queryStringParameters", {}) or event.get("filter", {})

    # Apply filters dynamically
    for key in ("user_email", "user_id", "service"):
        value = filter.get(key)
        if value is not None:
            df = df[df[key] == value]

    # convert the dataframe to json
    json = df.to_json(orient="records")

    return {
        "statusCode": 200,
        "body": json,
        "headers": {"Content-Type": "application/json"},
    }
