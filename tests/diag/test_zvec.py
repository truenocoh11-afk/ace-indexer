import os
import zvec
from sentence_transformers import SentenceTransformer
import time

def generate_sparse_vector(text):
    """
    Very naive sparse vector generation (BoW with TF).
    In a real scenario, this would use BM25 or something similar,
    or map tokens to vocabulary IDs.
    For Zvec, sparse vectors are typically dicts of {int: float}.
    We'll just hash words to ints for this simple test.
    """
    words = text.lower().split()
    word_counts = {}
    for word in words:
        if len(word) > 2: # Skip very short words
            word_hash = hash(word) % 1000000 # keep ids manageable
            word_counts[word_hash] = word_counts.get(word_hash, 0.0) + 1.0
    return word_counts

def run_test():
    print("Initializing embedding model...")
    # Using a small fast model for testing
    model = SentenceTransformer('all-MiniLM-L6-v2')
    dim = model.get_sentence_embedding_dimension()
    print(f"Model loaded. Dimension: {dim}")

    collection_path = "./zvec_test_db"
    
    # Ensure clean state
    if os.path.exists(collection_path):
        import shutil
        shutil.rmtree(collection_path)

    zvec.init(log_level=zvec.LogLevel.INFO)

    print("Defining schema...")
    schema = zvec.CollectionSchema(
        name="code_search",
        fields=[
            zvec.FieldSchema("path", zvec.DataType.STRING),
            zvec.FieldSchema("content", zvec.DataType.STRING),
            zvec.FieldSchema("type", zvec.DataType.STRING),
        ],
        vectors=[
            zvec.VectorSchema("dense_emb", zvec.DataType.VECTOR_FP32, dim),
            zvec.VectorSchema("sparse_emb", zvec.DataType.SPARSE_VECTOR_FP32),
        ]
    )

    print("Creating collection...")
    collection = zvec.create_and_open(collection_path, schema)

    print("Preparing sample documents...")
    samples = [
        {"path": "auth/login.py", "content": "def login(username, password):\n    # authenticates user\n    pass", "type": "backend"},
        {"path": "ui/Button.jsx", "content": "export function Button({onClick}) { return <button onClick={onClick}>Click</button> }", "type": "frontend"},
        {"path": "core/indexer.py", "content": "class Indexer:\n    def search(self, query):\n        # full text and semantic search\n        pass", "type": "backend"},
        {"path": "utils/hash.py", "content": "import hashlib\ndef compute_hash(data):\n    return hashlib.sha256(data).hexdigest()", "type": "backend"}
    ]

    docs_to_insert = []
    for i, sample in enumerate(samples):
        print(f"Embedding {sample['path']}...")
        dense = model.encode(sample["content"]).tolist()
        # Create a combined text for sparse to include path info
        sparse_text = sample['path'] + " " + sample['content']
        sparse = generate_sparse_vector(sparse_text)
        
        doc = zvec.Doc(
            id=f"doc_{i}",
            vectors={
                "dense_emb": dense,
                "sparse_emb": sparse
            },
            fields={
                "path": sample["path"],
                "content": sample["content"],
                "type": sample["type"]
            }
        )
        docs_to_insert.append(doc)

    print(f"Inserting {len(docs_to_insert)} documents...")
    collection.insert(docs_to_insert)
    collection.flush()
    print("Insertion complete.")

    # Test Search 1: Semantic
    print("\n--- Test 1: Pure Semantic Search ---")
    query_text = "how to verify user credentials"
    query_dense = model.encode(query_text).tolist()
    
    t0 = time.time()
    results = collection.query(
        vectors=[zvec.VectorQuery("dense_emb", vector=query_dense)],
        topk=2,
        output_fields=["path"]
    )
    t1 = time.time()
    for doc in results:
        print(f"  [{doc.score:.4f}] {doc.field('path')}")
    print(f"Time: {(t1-t0)*1000:.2f}ms")

    # Test Search 2: Hybrid (Semantic + Keyword)
    print("\n--- Test 2: Hybrid Search (Semantic + Exact Match) ---")
    query_text = "indexer search"
    query_dense = model.encode(query_text).tolist()
    query_sparse = generate_sparse_vector(query_text)
    
    t0 = time.time()
    results = collection.query(
        vectors=[
            zvec.VectorQuery("dense_emb", vector=query_dense),
            zvec.VectorQuery("sparse_emb", vector=query_sparse),
        ],
        topk=2,
        reranker=zvec.RrfReRanker(topn=5, rank_constant=60),
        output_fields=["path"]
    )
    t1 = time.time()
    for doc in results:
        print(f"  [{doc.score:.4f}] {doc.field('path')}")
    print(f"Time: {(t1-t0)*1000:.2f}ms")

    # Test Search 3: Hybrid + Filter
    print("\n--- Test 3: Hybrid + Metadata Filter ---")
    query_text = "hash"
    query_dense = model.encode(query_text).tolist()
    query_sparse = generate_sparse_vector(query_text)
    
    t0 = time.time()
    results = collection.query(
        vectors=[
            zvec.VectorQuery("dense_emb", vector=query_dense),
            zvec.VectorQuery("sparse_emb", vector=query_sparse),
        ],
        topk=2,
        filter="'backend' IN type", # Or type == 'backend', depending on zvec syntax
        reranker=zvec.WeightedReRanker(topn=5, metric=zvec.MetricType.L2, weights={"dense_emb": 0.3, "sparse_emb": 0.7}),
        output_fields=["path", "type"]
    )
    t1 = time.time()
    for doc in results:
        print(f"  [{doc.score:.4f}] {doc.field('path')} (Type: {doc.field('type')})")
    print(f"Time: {(t1-t0)*1000:.2f}ms")

    print("\nCleaning up...")
    collection.destroy()

if __name__ == "__main__":
    run_test()
