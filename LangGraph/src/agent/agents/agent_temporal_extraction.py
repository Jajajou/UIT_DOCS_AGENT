"""
Agent for extracting temporal metadata from documents.

This agent runs in the indexing pipeline after DeepSeek OCR to extract:
- Valid from/until dates
- Academic year information
- Student cohort applicability
- Document type classification
- Version information

Uses multi-strategy approach:
1. Regex patterns for Vietnamese date expressions (fast, high precision)
2. LLM-based extraction for complex cases (slower, better understanding)
3. Filename parsing as fallback (low confidence)
"""

import re
import hashlib
import dateparser
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field


class TemporalMetadata(BaseModel):
    """Structured output for temporal extraction."""

    valid_from: Optional[str] = Field(
        None,
        description="Start date in YYYY-MM-DD format when document becomes valid"
    )
    valid_until: Optional[str] = Field(
        None,
        description="End date in YYYY-MM-DD format when document expires"
    )
    academic_year: Optional[str] = Field(
        None,
        description="Academic year like '2024-2025'"
    )
    cohort_years: List[Union[int, str]] = Field(
        default_factory=list,
        description="Student cohorts this applies to. Use ['*'] for universal documents, [2024, 2025, ...] for specific cohorts, [] or null for unspecified"
    )
    cohort_scope: Optional[str] = Field(
        None,
        description="Cohort scope: 'universal' (all students), 'explicit' (specific cohorts), 'unspecified' (unclear)"
    )
    document_type: str = Field(
        "other",
        description="Type of document: regulation, announcement, tuition, scholarship, procedure, guide, other"
    )
    document_number: Optional[str] = Field(
        None,
        description="Official document number (e.g., '123/QĐ-ĐHCNTT')"
    )
    is_vbhn: bool = Field(
        False,
        description="True if this is a 'Văn bản hợp nhất' (Consolidated Document)"
    )
    amended_articles: List[str] = Field(
        default_factory=list,
        description="List of specific articles/clauses amended (e.g., ['Điều 5', 'Điều 12.1'])"
    )
    amends_documents: List[str] = Field(
        default_factory=list,
        description="List of document numbers that this document amends or supplements"
    )
    extraction_method: str = Field(
        "unknown",
        description="How dates were extracted: regex, dateparser, llm, filename, manual"
    )
    confidence: float = Field(
        0.0,
        description="Confidence score 0-1 for the extraction"
    )
    reasoning: str = Field(
        "",
        description="Explanation of how temporal info was extracted"
    )


class TemporalExtractionAgent:
    """
    Extracts temporal metadata from Vietnamese university documents.

    Designed for UIT documents where regulations have:
    - Specific validity periods
    - Academic year contexts
    - Student cohort applicability (6-year maximum study duration)
    - Document references (document number, amendments)
    - VBHN (Văn bản hợp nhất) status
    - Article-level overrides
    """

    def __init__(self, llm_model, config):
        """
        Initialize temporal extraction agent.

        Args:
            llm_model: LangChain LLM instance for complex extraction
            config: Agent configuration with temporal extraction settings
        """
        self.llm = llm_model
        self.config = config
        self.regex_patterns = self._load_vietnamese_patterns()

    def _load_vietnamese_patterns(self) -> Dict[str, List[str]]:
        """
        Load Vietnamese date extraction regex patterns.

        Patterns cover common Vietnamese temporal expressions in
        university regulations and announcements.

        Returns:
            Dictionary mapping pattern types to regex lists
        """
        return {
            "valid_from": [
                r"có hiệu lực từ ngày\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})",
                r"áp dụng từ\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})",
                r"bắt đầu từ\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})",
                r"hiệu lực kể từ\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})",
                r"thực hiện từ\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})",
            ],
            "valid_until": [
                r"hết hiệu lực vào\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})",
                r"đến hết\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})",
                r"có giá trị đến\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})",
                r"kết thúc vào\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})",
            ],
            "academic_year": [
                r"năm học\s+(\d{4})\s*[\-–]\s*(\d{4})",
                r"niên khóa\s+(\d{4})\s*[\-–]\s*(\d{4})",
                r"học kỳ.*năm\s+(\d{4})\s*[\-–]\s*(\d{4})",
            ],
            "cohort": [
                r"sinh viên khóa\s+(\d{4})",
                r"khóa tuyển\s+(\d{4})",
                r"đối với sinh viên nhập học năm\s+(\d{4})",
                r"sinh viên nhập học\s+(\d{4})",
                r"MSSV\s+(\d{4})\d+",  # Student ID pattern (year prefix)
            ],
            "version": [
                r"phiên bản\s+(\d+\.?\d*)",
                r"lần\s+(\d+)",
                r"v(\d+\.?\d*)",
                r"version\s+(\d+\.?\d*)",
            ],
            "document_number": [
                # Specific UIT patterns (high priority)
                r"ban hành kèm theo quyết định số\s*[:\.]?\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
                r"theo quyết định số\s*[:\.]?\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
                # Standard patterns
                r"số\s*[:\.]?\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)", # Số: 123/QĐ-ĐHCNTT
                r"số hiệu\s*[:\.]?\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
                r"^(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)$", # Line starts with Doc Number
            ],
            "amends": [
                r"sửa đổi.*?quyết định số\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
                r"bổ sung.*?quyết định số\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
                r"thay thế.*?quyết định số\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
                r"điều chỉnh.*?văn bản số\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
                r"căn cứ.*?quyết định số\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)", # Broad, careful with false positives
            ],
            "vbhn": [
                r"văn bản hợp nhất",
                r"hợp nhất các quy định",
                r"vbh\s*[n\.]",
            ],
            "amended_articles": [
                r"(điều\s+\d+\.?\d*)",
                r"(khoản\s+\d+\.?\d*)",
            ]
        }

    def _normalize_text(self, text: str) -> str:
        """Normalize Vietnamese text using underthesea."""
        try:
            from underthesea import text_normalize
            return text_normalize(text)
        except ImportError:
            return text

    def extract_with_local_tools(self, content: str) -> TemporalMetadata:
        """
        Extract dates using local tools (regex + dateparser).

        Args:
            content: Document text content

        Returns:
            TemporalMetadata with extracted information
        """
        # Normalize text first
        content = self._normalize_text(content)
        
        metadata = TemporalMetadata(extraction_method="local_tools") #type: ignore
        reasoning_parts = []

        # Check for VBHN
        for pattern in self.regex_patterns["vbhn"]:
            if re.search(pattern, content, re.IGNORECASE):
                metadata.is_vbhn = True
                reasoning_parts.append("Detected 'Văn bản hợp nhất' status")
                break

        # Extract dates with dateparser (higher priority than simple regex)
        # We look for date patterns near "có hiệu lực" or similar keywords
        date_keywords = ["có hiệu lực", "áp dụng", "bắt đầu", "ngày ban hành", "hết hiệu lực"]
        for kw in date_keywords:
            # Look for a date string in the 50 characters following the keyword
            match = re.search(f"{kw}.*?ngày\s+(\d{1,2}\s+(?:tháng|/)\s+\d{1,2}\s+(?:năm|/)\s+\d{4})", content, re.IGNORECASE | re.DOTALL)
            if match:
                date_str = match.group(1)
                dt = dateparser.parse(date_str, languages=['vi'])
                if dt:
                    iso_date = dt.strftime("%Y-%m-%d")
                    if "hết" in kw:
                        metadata.valid_until = iso_date
                        reasoning_parts.append(f"Parsed 'valid_until' with dateparser: {iso_date}")
                    else:
                        metadata.valid_from = iso_date
                        reasoning_parts.append(f"Parsed 'valid_from' with dateparser: {iso_date}")
                    metadata.confidence = max(metadata.confidence, 0.95)

        # Fallback to regex patterns if dateparser didn't catch everything
        if not metadata.valid_from:
            for pattern in self.regex_patterns["valid_from"]:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    day, month, year = match.groups()
                    metadata.valid_from = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    metadata.confidence = max(metadata.confidence, 0.9)
                    reasoning_parts.append(f"Found 'valid_from' date via regex: {metadata.valid_from}")
                    break

        if not metadata.valid_until:
            for pattern in self.regex_patterns["valid_until"]:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    day, month, year = match.groups()
                    metadata.valid_until = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    metadata.confidence = max(metadata.confidence, 0.9)
                    reasoning_parts.append(f"Found 'valid_until' date via regex: {metadata.valid_until}")
                    break

        # Extract academic year
        for pattern in self.regex_patterns["academic_year"]:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                start_year, end_year = match.groups()
                metadata.academic_year = f"{start_year}-{end_year}"
                reasoning_parts.append(f"Found academic year: {metadata.academic_year}")

                # Infer validity period from academic year if not already set
                if not metadata.valid_from:
                    metadata.valid_from = f"{start_year}-09-01"
                    reasoning_parts.append(f"Inferred valid_from from academic year: {metadata.valid_from}")
                if not metadata.valid_until:
                    metadata.valid_until = f"{end_year}-08-31"
                    reasoning_parts.append(f"Inferred valid_until from academic year: {metadata.valid_until}")

                metadata.confidence = max(metadata.confidence, 0.85)
                break

        # Extract cohorts
        cohort_set = set()
        for pattern in self.regex_patterns["cohort"]:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                # regex findall might return tuples if there are multiple groups, 
                # but our patterns have one group
                for m in matches:
                    try:
                        cohort_set.add(int(m))
                    except (ValueError, TypeError):
                        continue

        if cohort_set:
            base_cohorts = sorted(cohort_set)
            expanded_cohorts = []
            for cohort in base_cohorts:
                expanded_cohorts.extend(range(cohort, cohort + 6))

            metadata.cohort_years = sorted(set(expanded_cohorts))
            reasoning_parts.append(f"Found cohorts: {base_cohorts}, expanded for 6-year duration")

        # Extract document number
        doc_nums = []
        for pattern in self.regex_patterns["document_number"]:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                # Normalize slashes
                num = re.sub(r'\s*/\s*', '/', match.group(1))
                doc_nums.append(num)

        if doc_nums:
            # Filter and prioritize
            # 1. UIT specific numbers (contain ĐHCNTT or UIT)
            uit_nums = [n for n in doc_nums if any(k in n.upper() for k in ["ĐHCNTT", "UIT"])]
            
            # 2. Avoid higher level citations if possible
            exclude_keywords = ["QĐ-TTG", "NĐ-CP", "TT-BGDĐT", "BGDĐT"]
            preferred_nums = [n for n in uit_nums if not any(k in n.upper() for k in exclude_keywords)]
            
            if preferred_nums:
                metadata.document_number = preferred_nums[0]
            elif uit_nums:
                metadata.document_number = uit_nums[0]
            else:
                # Filter out generic ones from standard list
                filtered_generic = [n for n in doc_nums if not any(k in n.upper() for k in exclude_keywords)]
                if filtered_generic:
                    metadata.document_number = filtered_generic[0]
                else:
                    metadata.document_number = doc_nums[0]

            reasoning_parts.append(f"Found document number: {metadata.document_number}")

        # Extract amended documents
        amends_set = set()
        for pattern in self.regex_patterns["amends"]:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                # Normalize slashes in all found document numbers
                amends_set.update(re.sub(r'\s*/\s*', '/', m) for m in matches)
        
        # VBHN-specific consolidation extraction
        if metadata.is_vbhn:
            # Look for "Căn cứ..." or "Theo..." patterns which often list original docs in VBHN
            consolidation_patterns = [
                r"căn cứ\s+quyết định\s+số\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
                r"hợp nhất\s+quyết định\s+số\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
                r"quy định\s+tại\s+quyết định\s+số\s*(\d+\s*/\s*[A-ZĐƯĂÂÊÔƠ0-9\-]+)",
            ]
            for pattern in consolidation_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    amends_set.update(re.sub(r'\s*/\s*', '/', m) for m in matches)
            
            reasoning_parts.append(f"VBHN detected: extracted {len(amends_set)} consolidated references")
        
        if amends_set:
            metadata.amends_documents = sorted(list(amends_set))
            reasoning_parts.append(f"Found amended/consolidated documents: {metadata.amends_documents}")

        # Extract specific amended articles
        article_set = set()
        # Look for articles near amendment keywords (within 100 chars)
        amend_keywords = ["sửa đổi", "bổ sung", "thay thế", "điều chỉnh"]
        for kw in amend_keywords:
            # Find the keyword
            for match in re.finditer(kw, content, re.IGNORECASE):
                start = match.start()
                # Look in the next 200 characters for "Điều X" or "Khoản Y"
                window = content[start:start+200]
                for pattern in self.regex_patterns["amended_articles"]:
                    matches = re.findall(pattern, window, re.IGNORECASE)
                    if matches:
                        article_set.update(matches)
        
        if article_set:
            metadata.amended_articles = sorted(list(article_set))
            reasoning_parts.append(f"Found specific amended articles: {metadata.amended_articles}")

        metadata.reasoning = " | ".join(reasoning_parts) if reasoning_parts else "No temporal patterns found locally"

        return metadata

    async def extract_with_llm(self, content: str, filename: str) -> TemporalMetadata:
        """
        Extract temporal info using LLM when regex fails or for complex cases.

        Uses structured output to ensure consistent formatting.

        Args:
            content: Document text content (will be truncated for efficiency)
            filename: Document filename for context

        Returns:
            TemporalMetadata with LLM-extracted information
        """
        from agent.core.prompts import get_prompt, format_prompt

        # Use first 3000 chars to save tokens (temporal info usually in header)
        content_preview = content[:3000]

        prompt = format_prompt(
            get_prompt("temporal_extraction_system"),
            content=content_preview,
            filename=filename,
            current_year=datetime.now().year
        )

        # Call LLM with structured output
        try:
            # Use response_format for JSON mode if available
            response = await self.llm.with_structured_output(
                TemporalMetadata,
                method="json_mode"  # Force JSON mode instead of function calling
            ).ainvoke(prompt)
            response.extraction_method = "llm"
            return response
        except Exception as e:
            error_str = str(e)
            print(f"[Temporal Extraction LLM Error] {error_str}")

            # If error is JSON parsing from markdown code blocks, try to clean it
            if "Invalid JSON" in error_str and "```json" in error_str:
                try:
                    # Extract JSON from markdown code block
                    import re
                    json_match = re.search(r'```json\s*\n(.*?)\n```', error_str, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                        import json
                        data = json.loads(json_str)
                        response = TemporalMetadata(**data) #type: ignore
                        response.extraction_method = "llm"
                        print(f"[Temporal Extraction] ✓ Recovered from markdown JSON")
                        return response
                except Exception as recovery_error:
                    print(f"[Temporal Extraction] Failed to recover: {recovery_error}")

            # Return empty metadata on error
            return TemporalMetadata( #type: ignore
                extraction_method="llm",
                confidence=0.0,
                reasoning=f"LLM extraction failed: {error_str[:200]}"
            )

    def extract_from_filename(self, filename: str) -> TemporalMetadata:
        """
        Extract year/version from filename as fallback.

        Low confidence but better than nothing.

        Args:
            filename: Document filename

        Returns:
            TemporalMetadata with filename-based extraction
        """
        metadata = TemporalMetadata(extraction_method="filename") #type: ignore

        # Pattern: QuyDinh_2024.pdf or HocPhi_2024-2025.pdf
        year_match = re.search(r'(\d{4})', filename)
        if year_match:
            year = year_match.group(1)
            metadata.valid_from = f"{year}-01-01"
            metadata.valid_until = f"{year}-12-31"
            metadata.confidence = 0.5  # Low confidence
            metadata.reasoning = f"Extracted year {year} from filename (low confidence)"

        # Try to find academic year pattern in filename
        academic_year_match = re.search(r'(\d{4})[\-–](\d{4})', filename)
        if academic_year_match:
            start_year, end_year = academic_year_match.groups()
            metadata.academic_year = f"{start_year}-{end_year}"
            metadata.valid_from = f"{start_year}-09-01"
            metadata.valid_until = f"{end_year}-08-31"
            metadata.confidence = 0.6
            metadata.reasoning = f"Extracted academic year {metadata.academic_year} from filename"

        return metadata

    def _classify_document_type(self, filename: str, content: str) -> str:
        """
        Classify document type based on keywords.

        Args:
            filename: Document filename
            content: Document text content (first 2000 chars)

        Returns:
            Document type string
        """
        filename_lower = filename.lower()
        content_lower = content[:2000].lower()

        # Priority order for classification
        if any(kw in filename_lower or kw in content_lower for kw in ["quy định", "quy chế", "regulation"]):
            return "regulation"
        elif any(kw in filename_lower or kw in content_lower for kw in ["học phí", "tuition", "lệ phí", "học phí"]):
            return "tuition"
        elif any(kw in filename_lower or kw in content_lower for kw in ["học bổng", "scholarship"]):
            return "scholarship"
        elif any(kw in filename_lower or kw in content_lower for kw in ["thông báo", "announcement", "công bố"]):
            return "announcement"
        elif any(kw in filename_lower or kw in content_lower for kw in ["thủ tục", "procedure", "hướng dẫn", "guide"]):
            return "procedure"
        elif any(kw in filename_lower or kw in content_lower for kw in ["chính sách", "policy"]):
            return "policy"
        else:
            return "other"

    def _calculate_content_hash(self, content: str) -> str:
        """
        Calculate SHA-256 hash of content for change detection.

        Args:
            content: Document text content

        Returns:
            SHA-256 hash string with prefix
        """
        hash_obj = hashlib.sha256(content.encode('utf-8'))
        return f"sha256:{hash_obj.hexdigest()}"

    async def extract(
        self,
        content: str,
        filename: str,
        file_source: str
    ) -> Dict[str, Any]:
        """
        Main extraction method - tries multiple strategies in order.

        Strategy priority:
        1. Local tools (Regex + Dateparser)
        2. LLM (slower, better understanding for complex cases)
        3. Filename (fallback, low confidence)

        Args:
            content: Full document text content
            filename: Document filename
            file_source: Source URL or path

        Returns:
            Metadata dictionary ready to attach to document
        """
        # Strategy 1: Local tools (fast, high precision)
        local_result = self.extract_with_local_tools(content)

        # If local tools found dates with high confidence, use it
        if local_result.valid_from and local_result.confidence >= 0.8:
            result = local_result
            print(f"[Temporal Extraction] Using local tools result (confidence: {result.confidence})")
        else:
            # Strategy 2: LLM (slower, better understanding)
            llm_result = await self.extract_with_llm(content, filename)

            # Merge results (use whichever is more confident)
            if llm_result.confidence > local_result.confidence:
                result = llm_result
                print(f"[Temporal Extraction] Using LLM result (confidence: {result.confidence})")
            else:
                result = local_result
                print(f"[Temporal Extraction] Using local tools result (confidence: {result.confidence})")

        # Strategy 3: Filename fallback (Merge missing fields)
        filename_result = self.extract_from_filename(filename)

        if filename_result.confidence > 0:
            merged_info = []
            
            # Fill valid_from/until if missing
            if not result.valid_from and filename_result.valid_from:
                result.valid_from = filename_result.valid_from
                result.valid_until = filename_result.valid_until
                merged_info.append("dates from filename")
                
                # If we rely entirely on filename for dates, ensure confidence isn't 0
                if result.confidence == 0:
                    result.confidence = filename_result.confidence
                    result.extraction_method = "filename_fallback"

            # Fill academic_year if missing
            if not result.academic_year and filename_result.academic_year:
                result.academic_year = filename_result.academic_year
                merged_info.append("academic year from filename")

            if merged_info:
                print(f"[Temporal Extraction] Merged info: {', '.join(merged_info)}")
                result.reasoning += f" | Merged: {', '.join(merged_info)}"

        # Classify document type
        result.document_type = self._classify_document_type(filename, content)

        # Calculate content hash for change detection
        content_hash = self._calculate_content_hash(content)

        # Convert to metadata dict for LightRAG
        metadata = {
            # Temporal information
            "valid_from": result.valid_from,
            "valid_until": result.valid_until,
            "academic_year": result.academic_year,
            "cohort_years": result.cohort_years,

            # Document classification
            "document_type": result.document_type,
            "document_number": result.document_number,
            "is_vbhn": result.is_vbhn,
            "amended_articles": result.amended_articles,

            # Document relationships
            "amends_documents": result.amends_documents,
            "amended_by": [], # Will be populated by reverse linking logic

            # Extraction metadata
            "temporal_extraction_method": result.extraction_method,
            "temporal_confidence": result.confidence,
            "temporal_reasoning": result.reasoning,

            # Lifecycle tracking
            "indexed_at": datetime.now().isoformat(),
            "content_hash": content_hash,

            # Version tracking (will be populated by version detection logic)
            "document_version": None,
            "version_number": 1,
            "supersedes": [],
            "superseded_by": None,

            # Soft delete flags
            "is_archived": False,
            "archived_at": None,
            "archive_reason": None,

            # Source information
            "file_source": file_source,
        }

        return metadata


# Graph node function for LangGraph integration
async def extract_temporal_metadata_node(state: dict) -> Dict[str, Any]:
    """
    LangGraph node: Extract temporal metadata from parsed document.

    Runs in indexing pipeline before uploading to LightRAG.

    Args:
        state: IndexingState dictionary

    Returns:
        Updated state with temporal metadata
    """
    from agent.config import settings
    from langchain.chat_models import init_chat_model

    # Get data from previous nodes
    parsed_content = state.get("parsed_content", "")
    file_path = state.get("file_path", "")
    file_source = state.get("file_source", "")
    filename = file_path.split("/")[-1] if file_path else "unknown"

    if not parsed_content:
        print(f"[Temporal Extraction] WARNING: No parsed content found for {filename}")
        return {
            "document_metadata": {},
            "temporal_extraction_complete": False
        }

    # Initialize LLM for extraction
    llm = init_chat_model(
        model_provider="openai",
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.llm_model,
        streaming=False,
        temperature=0.1,
        model_kwargs={"tool_choice": "none"}
    )

    # Initialize agent
    agent = TemporalExtractionAgent(llm, settings)

    # Extract metadata
    print(f"\n[Temporal Extraction] 📅 Processing: {filename}")
    temporal_metadata = await agent.extract(
        content=parsed_content,
        filename=filename,
        file_source=file_source
    )

    # Log results
    print(f"  ├─ Type: {temporal_metadata.get('document_type')}")
    print(f"  ├─ Doc Number: {temporal_metadata.get('document_number') or 'N/A'}")
    print(f"  ├─ Valid: {temporal_metadata.get('valid_from') or 'N/A'} → {temporal_metadata.get('valid_until') or 'N/A'}")
    print(f"  ├─ Academic Year: {temporal_metadata.get('academic_year') or 'N/A'}")
    if temporal_metadata.get('cohort_years'):
        cohorts = temporal_metadata['cohort_years']
        print(f"  ├─ Cohorts: {cohorts[:3]}{'...' if len(cohorts) > 3 else ''} ({len(cohorts)} total)")
    if temporal_metadata.get('amends_documents'):
        print(f"  ├─ Amends: {temporal_metadata.get('amends_documents')}")
    print(f"  ├─ Method: {temporal_metadata.get('temporal_extraction_method')}")
    print(f"  └─ Confidence: {temporal_metadata.get('temporal_confidence'):.2f}")

    # Merge with existing metadata from previous nodes
    existing_metadata = state.get("document_metadata", {})
    existing_metadata.update(temporal_metadata)

    return {
        "document_metadata": existing_metadata,
        "temporal_extraction_complete": True
    }
