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
    amends_documents: List[str] = Field(
        default_factory=list,
        description="List of document numbers that this document amends or supplements"
    )
    extraction_method: str = Field(
        "unknown",
        description="How dates were extracted: regex, llm, filename, manual"
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
                r"số\s*[:\.]?\s*(\d+/[A-ZĐƯ0-9\-]+)", # Số: 123/QĐ-ĐHCNTT
                r"số hiệu\s*[:\.]?\s*(\d+/[A-ZĐƯ0-9\-]+)",
                r"^(\d+/[A-ZĐƯ0-9\-]+)$", # Line starts with Doc Number
            ],
            "amends": [
                r"sửa đổi.*quyết định số\s*(\d+/[A-ZĐƯ0-9\-]+)",
                r"bổ sung.*quyết định số\s*(\d+/[A-ZĐƯ0-9\-]+)",
                r"thay thế.*quyết định số\s*(\d+/[A-ZĐƯ0-9\-]+)",
                r"điều chỉnh.*văn bản số\s*(\d+/[A-ZĐƯ0-9\-]+)",
                r"căn cứ.*quyết định số\s*(\d+/[A-ZĐƯ0-9\-]+)", # Broad, careful with false positives
            ]
        }

    def extract_with_regex(self, content: str) -> TemporalMetadata:
        """
        Extract dates using regex patterns.

        Fast and accurate for well-formatted Vietnamese documents.

        Args:
            content: Document text content

        Returns:
            TemporalMetadata with extracted information
        """
        metadata = TemporalMetadata(extraction_method="regex") #type: ignore
        reasoning_parts = []

        # Extract valid_from date
        for pattern in self.regex_patterns["valid_from"]:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                day, month, year = match.groups()
                metadata.valid_from = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                metadata.confidence = 0.9
                reasoning_parts.append(f"Found 'valid_from' date: {metadata.valid_from}")
                break

        # Extract valid_until date
        for pattern in self.regex_patterns["valid_until"]:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                day, month, year = match.groups()
                metadata.valid_until = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                metadata.confidence = max(metadata.confidence, 0.9)
                reasoning_parts.append(f"Found 'valid_until' date: {metadata.valid_until}")
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
                cohort_set.update(int(y) for y in matches)

        if cohort_set:
            # UIT requirement: Students have max 6 years to study
            # If a regulation mentions cohort 2024, it applies to students enrolled 2024-2029
            base_cohorts = sorted(cohort_set)
            expanded_cohorts = []
            for cohort in base_cohorts:
                # Regulation applies for 6 years from cohort start
                expanded_cohorts.extend(range(cohort, cohort + 6))

            metadata.cohort_years = sorted(set(expanded_cohorts))
            reasoning_parts.append(f"Found cohorts: {base_cohorts}, expanded for 6-year duration: {metadata.cohort_years[:3]}...")

        # Extract document number
        for pattern in self.regex_patterns["document_number"]:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                metadata.document_number = match.group(1)
                reasoning_parts.append(f"Found document number: {metadata.document_number}")
                break

        # Extract amended documents
        amends_set = set()
        for pattern in self.regex_patterns["amends"]:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                amends_set.update(matches)
        
        if amends_set:
            metadata.amends_documents = sorted(list(amends_set))
            reasoning_parts.append(f"Found amended documents: {metadata.amends_documents}")

        metadata.reasoning = " | ".join(reasoning_parts) if reasoning_parts else "No temporal patterns found"

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
        1. Regex (fast, high precision for Vietnamese patterns)
        2. LLM (slower, better understanding for complex cases)
        3. Filename (fallback, low confidence)

        Args:
            content: Full document text content
            filename: Document filename
            file_source: Source URL or path

        Returns:
            Metadata dictionary ready to attach to document
        """
        # Strategy 1: Regex (fast, high precision)
        regex_result = self.extract_with_regex(content)

        # If regex found dates with high confidence, use it
        if regex_result.valid_from and regex_result.confidence >= 0.8:
            result = regex_result
            print(f"[Temporal Extraction] Using regex result (confidence: {result.confidence})")
        else:
            # Strategy 2: LLM (slower, better understanding)
            llm_result = await self.extract_with_llm(content, filename)

            # Merge results (use whichever is more confident)
            if llm_result.confidence > regex_result.confidence:
                result = llm_result
                print(f"[Temporal Extraction] Using LLM result (confidence: {result.confidence})")
            else:
                result = regex_result
                print(f"[Temporal Extraction] Using regex result (confidence: {result.confidence})")

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
