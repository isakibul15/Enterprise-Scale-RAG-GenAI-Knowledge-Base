# Import directly from the specific module files, not from this package.
# e.g. from app.retrieval.chain import ask
#      from app.retrieval.vector_store import get_langchain_vector_store
#
# Eager package-level re-exports here cause a circular import:
#   retrieval/__init__ → vector_store → ingestion/__init__ → pipeline → vector_store

