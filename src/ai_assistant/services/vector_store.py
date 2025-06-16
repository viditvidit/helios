"""
Manages the vector store for Retrieval-Augmented Generation (RAG).
Handles file chunking, embedding, indexing, and searching with lazy loading to prevent fork-related warnings and improve startup time.
"""
import pickle
from pathlib import Path
from typing import List, Dict, Any
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import faiss
from rich.console import Console
from rich.progress import track
from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter

from ..core.config import Config

console = Console()

class VectorStore:
    INDEX_FILE = ".helios/vector_index.faiss"
    METADATA_FILE = ".helios/metadata.pkl"
    EMBEDDING_MODEL = 'all-MiniLM-L6-v2'

    def __init__(self, config: Config):
        self.config = config
        self.index_path = Path(self.INDEX_FILE)
        self.metadata_path = Path(self.METADATA_FILE)
        
        # --- THE FIX: LAZY LOADING ---
        # Initialize resources to None. They will be loaded on first use via properties.
        self._embedding_model: SentenceTransformer | None = None
        self._index: faiss.Index | None = None
        self._metadata: List[Dict[str, Any]] | None = None

    @property
    def embedding_model(self) -> SentenceTransformer:
        """Lazy-loads the sentence transformer model when first accessed."""
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer(self.EMBEDDING_MODEL)
        return self._embedding_model

    @property
    def index(self) -> faiss.Index | None:
        """Lazy-loads the FAISS index from disk when first accessed."""
        if self._index is None:
            if self.index_path.exists():
                try:
                    self._index = faiss.read_index(str(self.index_path))
                except Exception as e:
                    console.print(f"[red]Error loading FAISS index: {e}[/red]")
            else:
                 console.print("[bold yellow]Warning:[/bold yellow] No vector index found. Please run `helios index` for contextual answers.")
        return self._index
    
    @property
    def metadata(self) -> List[Dict[str, Any]]:
        """Lazy-loads the metadata from disk when first accessed."""
        if self._metadata is None:
            if self.metadata_path.exists():
                try:
                    with open(self.metadata_path, "rb") as f:
                        self._metadata = pickle.load(f)
                except Exception as e:
                    console.print(f"[red]Error loading metadata: {e}[/red]")
                    self._metadata = []
            else:
                self._metadata = []
        return self._metadata

    def save(self):
        """Saves the FAISS index and metadata to disk."""
        if self._index is None or self._metadata is None:
            console.print("[yellow]Nothing to save. Index or metadata not generated.[/yellow]")
            return
            
        self.index_path.parent.mkdir(exist_ok=True)
        faiss.write_index(self._index, str(self.index_path))
        with open(self.metadata_path, "wb") as f:
            pickle.dump(self._metadata, f)

    def index_files(self, file_contents: Dict[str, str]):
        """Chunks, embeds, and indexes repository files."""
        if not file_contents:
            console.print("[yellow]No files provided for indexing.[/yellow]")
            return

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=100
        )
        
        all_chunks_text = []
        self._metadata = [] # Reset metadata before re-indexing

        for file_path, content in track(file_contents.items(), description="[dim][cyan]Chunking files...[/cyan][/dim]"):
            chunks = text_splitter.split_text(content)
            for i, chunk in enumerate(chunks):
                all_chunks_text.append(chunk)
                self._metadata.append({"file_path": file_path, "chunk_index": i, "text": chunk})

        if not all_chunks_text:
            console.print("[yellow]No text chunks were generated from files.[/yellow]")
            return
            
        with console.status("[bold yellow]Creating embeddings...[/bold yellow]", spinner="point"):
            embeddings = self.embedding_model.encode(all_chunks_text, show_progress_bar=False)
        
        dimension = embeddings.shape[1]
        self._index = faiss.IndexFlatL2(dimension)
        self._index.add(embeddings)
        
        console.print(f"[dim][green]Generated and indexed {self._index.ntotal} text chunks.[/green][/dim]")
        self.save()
        console.print(f"[dim][green]Index saved to {self.index_path}[/green][/dim]")


    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Searches the vector store, triggering lazy loading if needed."""
        if self.index is None or not self.metadata:
            return []

        # This line will trigger lazy loading of the embedding_model
        query_embedding = self.embedding_model.encode([query], show_progress_bar=False)
        distances, indices = self.index.search(query_embedding, k)
        
        results = [self.metadata[i] for i in indices[0] if i != -1]
        
        return results
    
    def clear(self):
        """Clears the vector store by resetting index and metadata."""
        self._index = None
        self._metadata = None
        console.print("[dim]Vector store cleared.[/dim]")