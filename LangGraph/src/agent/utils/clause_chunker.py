import re
from typing import List, Dict, Any, Optional
from lightrag.utils import Tokenizer
from lightrag.operate import chunking_by_token_size

# Pattern for Vietnamese legal clauses: "Điều 1:", "Điều 2.", etc.
# Supports both "Điều" and "Dieu" (though prompt emphasized proper 'Đ')
DIEU_PATTERN = re.compile(r'^((?:Điều|Dieu|ĐIỀU)\s+(\d+[a-z]?))\s*[.:]', re.MULTILINE | re.IGNORECASE)

def clause_aware_chunking_func(
    tokenizer: Tokenizer,
    content: str,
    split_by_character: Optional[str] = None,
    split_by_character_only: bool = False,
    overlap_tokens: int = 100,
    max_tokens: int = 1200
) -> List[Dict[str, Any]]:
    """
    Splits content into chunks based on legal clauses (Điều).
    
    If fewer than 2 clauses are found, falls back to default LightRAG chunking.
    If a clause is longer than max_tokens, it's sub-split by paragraphs.
    """
    
    # Find all clause markers and their positions
    matches = list(DIEU_PATTERN.finditer(content))
    
    if len(matches) < 2:
        # Fallback to default chunking
        return chunking_by_token_size(
            tokenizer=tokenizer,
            content=content,
            split_by_character=split_by_character,
            split_by_character_only=split_by_character_only,
            chunk_overlap_token_size=overlap_tokens,
            chunk_token_size=max_tokens
        )

    chunks = []
    
    # Process content between clause markers
    for i in range(len(matches)):
        start_pos = matches[i].start()
        end_pos = matches[i+1].start() if i + 1 < len(matches) else len(content)
        
        clause_id = matches[i].group(1) # e.g. "Điều 5"
        clause_num_str = matches[i].group(2) # e.g. "5"
        
        try:
            # Extract integer part if it has a suffix like '5a'
            clause_number = int(re.match(r'(\d+)', clause_num_str).group(1))
        except (ValueError, AttributeError):
            clause_number = None

        clause_content = content[start_pos:end_pos].strip()
        clause_tokens = tokenizer.encode(clause_content)
        
        if len(clause_tokens) <= max_tokens:
            chunks.append({
                "content": clause_content,
                "tokens": len(clause_tokens),
                "chunk_order_index": len(chunks),
                "clause_id": clause_id,
                "clause_number": clause_number
            })
        else:
            # Sub-split long clause by paragraphs
            paragraphs = re.split(r'\n\s*\n', clause_content)
            current_sub_content = ""
            
            for para in paragraphs:
                para = para.strip()
                if not para: continue
                
                para_tokens = tokenizer.encode(para)
                
                # If a single paragraph is too long, we might need even finer splitting,
                # but for now we follow the instruction "sub-split clauses... by paragraphs".
                # We combine paragraphs until they reach max_tokens.
                
                potential_content = (current_sub_content + "\n\n" + para) if current_sub_content else para
                potential_tokens = len(tokenizer.encode(potential_content))
                
                if potential_tokens <= max_tokens:
                    current_sub_content = potential_content
                else:
                    # Flush current sub-content
                    if current_sub_content:
                        chunks.append({
                            "content": current_sub_content,
                            "tokens": len(tokenizer.encode(current_sub_content)),
                            "chunk_order_index": len(chunks),
                            "clause_id": clause_id,
                            "clause_number": clause_number
                        })
                    
                    # If the single paragraph is still too long, use default chunking on it
                    if len(para_tokens) > max_tokens:
                        sub_chunks = chunking_by_token_size(
                            tokenizer=tokenizer,
                            content=para,
                            chunk_overlap_token_size=overlap_tokens,
                            chunk_token_size=max_tokens
                        )
                        for sc in sub_chunks:
                            chunks.append({
                                "content": sc["content"],
                                "tokens": sc["tokens"],
                                "chunk_order_index": len(chunks),
                                "clause_id": clause_id,
                                "clause_number": clause_number
                            })
                        current_sub_content = ""
                    else:
                        current_sub_content = para
            
            # Flush final sub-content
            if current_sub_content:
                chunks.append({
                    "content": current_sub_content,
                    "tokens": len(tokenizer.encode(current_sub_content)),
                    "chunk_order_index": len(chunks),
                    "clause_id": clause_id,
                    "clause_number": clause_number
                })
                
    return chunks
