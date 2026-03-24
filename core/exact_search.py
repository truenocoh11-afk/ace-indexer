import sqlite3
import os
import sys

class TrigramIndex:
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS trigrams (gram TEXT, doc_id TEXT)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gram ON trigrams(gram)")
            conn.commit()
        finally:
            conn.close()

    def generate_trigrams(self, text):
        # Trigrams for substring matching
        if len(text) < 3:
            return {text}
        return {text[i:i+3] for i in range(len(text) - 2)}

    def index_document(self, doc_id, text):
        grams = self.generate_trigrams(text)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM trigrams WHERE doc_id = ?", (doc_id,))
            conn.executemany("INSERT INTO trigrams (gram, doc_id) VALUES (?, ?)", 
                             [(g, doc_id) for g in grams])
            conn.commit()
        finally:
            conn.close()

    def index_documents_batch(self, documents):
        """Indexes multiple documents in a single SQLite transaction."""
        if not documents:
            return
        conn = sqlite3.connect(self.db_path)
        try:
            doc_ids = [(d[0],) for d in documents]
            # Batch delete old entries
            conn.executemany("DELETE FROM trigrams WHERE doc_id = ?", doc_ids)
            
            # Generate all grams and batch insert
            all_grams = []
            for doc_id, text in documents:
                grams = self.generate_trigrams(text)
                all_grams.extend([(g, doc_id) for g in grams])
            
            conn.executemany("INSERT INTO trigrams (gram, doc_id) VALUES (?, ?)", all_grams)
            conn.commit()
        except Exception as e:
            sys.stderr.write(f"[TrigramIndex] Batch indexing error: {e}\n")
        finally:
            conn.close()

    def find_candidates(self, query_text):
        if not query_text:
            return []
            
        grams = list(self.generate_trigrams(query_text))
        if not grams:
            return []

        conn = sqlite3.connect(self.db_path)
        try:
            # INTERSECT approach: finding docs that contain ALL trigrams of the query
            query = "SELECT doc_id FROM trigrams WHERE gram = ?"
            for _ in range(len(grams) - 1):
                query += " INTERSECT SELECT doc_id FROM trigrams WHERE gram = ?"
            
            cursor = conn.execute(query, grams)
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            sys.stderr.write(f"[TrigramIndex] Search error: {e}\n")
            return []
        finally:
            conn.close()
    def delete_documents(self, file_paths):
        """Removes all trigrams associated with the given file paths or their chunks."""
        if not file_paths:
            return
        conn = sqlite3.connect(self.db_path)
        try:
            # We use LIKE with a prefix to catch both the file ID and its chunks (file::symbol)
            for path in file_paths:
                conn.execute("DELETE FROM trigrams WHERE doc_id = ? OR doc_id LIKE ? || '::%'", (path, path))
            conn.commit()
        except Exception as e:
            sys.stderr.write(f"[TrigramIndex] Cleanup error: {e}\n")
        finally:
            conn.close()
