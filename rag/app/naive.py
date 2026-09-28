import tiktoken
import re

def num_tokens(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))

def chunk(text: str, chunk_size: int = 512, overlap: int = 50) -> list:
    """MVP Naive Text Chunker using tiktoken and basic delimiters."""
    # Split by double newline first (paragraphs)
    paragraphs = re.split(r'\n\s*\n', text)
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for p in paragraphs:
        p_len = num_tokens(p)
        
        # If a single paragraph is too long, forcefully split it by sentences (crude MVP split)
        if p_len > chunk_size:
            sentences = re.split(r'(?<=[.!?])\s+', p)
            for s in sentences:
                s_len = num_tokens(s)
                if current_length + s_len > chunk_size:
                    chunks.append(" ".join(current_chunk))
                    # Retain overlap (last N elements that fit in overlap budget)
                    overlap_len = 0
                    overlap_chunk = []
                    for c in reversed(current_chunk):
                        c_len = num_tokens(c)
                        if overlap_len + c_len <= overlap:
                            overlap_chunk.insert(0, c)
                            overlap_len += c_len
                        else:
                            break
                    current_chunk = overlap_chunk
                    current_length = overlap_len
                
                current_chunk.append(s)
                current_length += s_len
            continue
            
        if current_length + p_len > chunk_size:
            chunks.append("\n\n".join(current_chunk))
            # overlap logic
            overlap_len = 0
            overlap_chunk = []
            for c in reversed(current_chunk):
                c_len = num_tokens(c)
                if overlap_len + c_len <= overlap:
                    overlap_chunk.insert(0, c)
                    overlap_len += c_len
                else:
                    break
            current_chunk = overlap_chunk
            current_length = overlap_len
            
        current_chunk.append(p)
        current_length += p_len
        
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
        
    # Return array of dicts mapping RAGFlow schema
    result = []
    for txt in chunks:
        result.append({
            "content_with_weight": txt,
            "content": txt,
            "token_num": num_tokens(txt)
        })
        
    return result
