from openai import OpenAI

def generate_embedding(text, api_key):
    client = OpenAI(api_key=api_key)

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=512,
    )

    return response.data[0].embedding