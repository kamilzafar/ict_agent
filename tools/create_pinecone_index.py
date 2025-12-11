"""Script to create a Pinecone index with 512 dimensions for OpenAI small embeddings."""
import os
from dotenv import load_dotenv
from pinecone import Pinecone

# Load environment variables
load_dotenv()

def create_index():
    """Create a Pinecone index with 512 dimensions."""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY not set in environment")
    
    index_name = os.getenv("PINECONE_INDEX_NAME", "default-index")
    
    # Initialize Pinecone
    pc = Pinecone(api_key=api_key)
    
    # Check if index already exists
    existing_indexes = [index.name for index in pc.list_indexes()]
    
    if index_name in existing_indexes:
        print(f"Index '{index_name}' already exists.")
        index_info = pc.describe_index(index_name)
        print(f"Current dimension: {index_info.dimension}")
        if index_info.dimension != 512:
            print(f"Warning: Index dimension is {index_info.dimension}, but we're using 512 dimensions.")
            print("You may need to create a new index with the correct dimension.")
        return
    
    # Create index with 512 dimensions (for OpenAI small embeddings)
    print(f"Creating index '{index_name}' with 512 dimensions...")
    pc.create_index(
        name=index_name,
        dimension=512,  # OpenAI text-embedding-3-small dimension
        metric="cosine"
    )
    
    print(f"✓ Index '{index_name}' created successfully!")
    print(f"  Dimension: 512")
    print(f"  Metric: cosine")
    print(f"  Model: text-embedding-3-small")

if __name__ == "__main__":
    try:
        create_index()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

