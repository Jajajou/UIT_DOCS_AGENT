# AI-SPEC.md

## 1a. System Overview
**System Type**: Multi-Agent RAG (Retrieval-Augmented Generation)
**Use Case**: Vietnamese language higher education student information retrieval system for Ho Chi Minh City University of Information Technology (UIT)
**Output Type**: Question-answering system with hyperlinked references to official documents

## 1b. Domain Context

### Educational Domain Specifics

**Industry Vertical**: Vietnamese Higher Education Administration
**Institution Focus**: Ho Chi Minh City University of Information Technology (UIT) - 越南国家大学胡志明市信息技术大学
**User Population**:
- Current students across all academic years (2021-2026 cohorts)
- Prospective students and applicants
- University administrative staff and faculty
- Researchers and policy examiners

**Stakes Level**: **HIGH**
- **Critical Academic Decisions**: Degree requirements, graduation eligibility, transfer policies
- **Financial Impact**: Tuition calculations, scholarship eligibility, payment deadlines
- **Legal Compliance**: Vietnam Education Law, MOET (Ministry of Education and Training) regulations
- **Institutional Risk**: Accreditation compliance, audit trails, documentation accuracy

**Document Consequence**: When AI output is incorrect at **DOWNSTREAM IMPACT**
- Student may enroll in wrong courses → delayed graduation
- Incorrect fee calculations → financial disputes
- Outdated policy information → administrative appeals
- Wrong degree requirements → academic probation

### Vietnamese Higher Education System Framework

**Regulatory Context**:
- Centralized Vietnamese MOET (Bộ GD&ĐT) oversight with all institutions following National Qualification Framework
- Required compliance with Education Law, Higher Education Law, and recent Digital Education Decree No. 1705/QĐ-TTg (December 31, 2024)
- Administrative burden from multi-stakeholder regulations (MOET academic workload, Cabinet academic salary standards, Prime Ministerial professorial requirements)

**Document Types in Practice**:
1. **Academic Regulations** (`Quy chế đào tạo`): Undergraduate/graduate program completion requirements
2. **Course Catalogs** (`Chương trình đào tạo`): Individual course descriptions, prerequisites, credit hours
3. **Admission Policies** (`Quy chế tuyển sinh`): Entrance requirements, quota calculations, ethnic minority policies
4. **Administrative Procedures** (`Quy trình hành chính`): Student services, diploma issuance, transcript authentication
5. **Amendment Documents** (`Sửa đổi, bổ sung`): Policy changes overriding previous documents
6. **Announcement Circulars** (`Thông báo`): Current semester information, exam schedules, fee deadlines

### Temporal Aspects Critical to Domain Success

**Cohort-Dependent Variations**:
- Same regulation applies differently to different enrollment years (e.g., Vietnamese language proficiency required for 2025+ cohorts only)
- Tuition structures may vary by cohort based on policy changes
- Graduation requirements adjusted annually by MOET directives
- Bridge programs for transfer students from previous academic systems

**Document Validity Windows**:
- Academic Year-based validity ("2024-2025 academic year")
- Semester-specific policies (fall/spring continuous modifications)
- Policy supersession patterns (new regulation replaces old via `Sửa đổi toàn bộ...` clauses)
- Soft-expiration vs hard-expiration documents (historical queries still needed)

**Temporal Metadata Requirements**:
- `document_number`: Official document identifier following Vietnamese format (e.g., "108/QĐ-ĐHCNTT", "45/QĐ-SDH")
- `valid_from`, `valid_until`: Document enforcement periods (probably YYYY-MM-DD format, Vietnamese locale)
- `academic_year`: Vietnamese academic year format (2024-2025, 2025-2026)
- `cohort_years`: Specific year cohorts affected (e.g., [2022, 2023, 2024, 2025, 2026])
- `amends_documents`: Bidirectional links between old/new policy documents
- `is_archived`: Soft delete for expired documents (maintain historical accessibility)

### Stakeholder Role Complexity

**Primary User Roles**:
| Role | Examine for Evaluation |
|------|----------------------|
| **Current Student** | Cohort-specific policy accuracy, tuition calculation precision, deadline clarity |
| **Prospective Student** | Admission requirements sensitivity to changes, program-specific regulations |
| **Academic Advisor** | Degree audit accuracy, course sequence validation, policy exception handling |
| **Registrar Staff** | Administrative procedure reliability, form requirement completeness |
| **Faculty** | Course development policies, grading regulations, academic integrity |
| **Vietnamese MOET Inspector** | Legal compliance verification, document authenticity confirmation |

**Secondary Stakeholder Conflicts**:
- Academic vs administrative workflow priorities
- Central MOET requirements vs local institutional flexibility
- Student convenience vs bureaucratic accuracy requirements
- English vs Vietnamese language document dualism

### Domain-Specific Evaluation Criteria

The following criteria must measured specifically for Vietnamese higher education experts evaluating this system:

#### Dimension: Document Currency and Precision
**Good (domain expert would accept)**:
- Response identifies exactly which document numbers apply to specific academic year/cohort combinations
- Provides both current regulation AND references superseded document with amendment tracking
- Distinguishes between "currently valid" vs "historically valid" documents clearly
**Bad (domain expert would flag)**:
- Returns 2024 graduation requirements for 2022 cohort students without warning
- References "University policies" without identifying specific document numbers or dates
- Fails to mention recent curriculum changes affecting ongoing students
**Stakes**: **CRITICAL** - students may follow wrong graduation requirements
**Source**: Vietnamese MOET document management standards - expired documents constitute unenforceable policies

#### Dimension: Vietnamese Regulatory Compliance Language
**Good**:
- Uses precise Vietnamese administrative terminology ("Quy chế đào tạo", "Sửa đổi, bổ sung", "Quyết định" etc.)
- Respects Vietnamese academic calendar (academic year beginning September, two semesters vs quarters)
- Handles Vietnamese numerical format (commas vs periods, date formats)
**Bad**:
- Uses English approximations for Vietnamese administrative concepts
- Applies US-style academic calendar interpretation to Vietnamese university schedule
- Translations that lose administrative precision ("President" vs "Hiệu trưởng")
**Stakes**: **HIGH** - mistranslation creates compliance risks
**Source**: MOET Administrative Language Standards

#### Dimension: Cohort-Specific Policy Application
**Good**:
- Explicitly states "This policy applies to students enrolled 2023-2026, MEANWHILE 2022 cohort follows previous regulation"
- Provides migration policy for transfer students between cohorts
- Differentiates international student requirements from domestic student policies
**Bad**:
- Generic policy statements without cohort disclaimers
- Fails to identify which policies grandfather existing students
- Ignores bridge policy for students transferring between degree programs
**Stakes**: **HIGH** - may force policy violations or unnecessary course retakes
**Source**: Vietnamese university regulatory compliance memos

#### Dimension: Financial Policy Accuracy
**Good**:
- Provides exact tuition calculation methods for specific academic years
- Identifies scholarship eligibility rules with income verification requirements
- Lists payment deadline consequences with Vietnamese banking procedures
**Bad**:
- Rounded estimates instead of precise calculations
- Misses income-based fee waivers or ethnic minority reductions
- Incomplete payment instruction details (Vietnamese banking vs international transfers)
**Stakes**: **HIGH** - financial disputes with government agencies
**Source**: Vietnamese Ministry of Education financial regulation protocols

### Known Failure Modes in Vietnamese Higher Education Context

**Temporal Collisions (Document Version Chaos)**:
- Student asking "What are graduation requirements?" receiving contradictory information from 2023 vs 2024 documents
- Amendment documents creating policy confusion when they modify degree requirements mid-stream
- International student confused by policy changes during enrollment process

**Cohort Boundary Errors**:
- Transfer student receiving degree requirements for wrong starting year
- Student-athlete denied scholarship due to policy change for different cohort
- Alumni verification discrepancies between transcript sources

**MOET Compliance Violations**:
- Incorrect interpretation of Vietnamese-language administrative procedures
- Missing required verification documents for government scholarship applications
- Failure to follow Vietnamese academic calendar deadlines
- Missing authentication steps for government recognition requests

**Document Language Mismatches**:
- English summary missing critical Vietnamese-specific administrative terminology
- Automated translation losing quantitative precision in fee calculations
- Cultural context stripping (e.g., Vietnamese scholastic honor systems vs Western GPA)

### Regulatory and Compliance Framework

**Direct Relevant Regulations**:
- **Education Law 2019** (Luật Giáo dục) - Foundation for all university governance
- **Government Decree 1705/QĐ-TTg** (December 31, 2024) - Digital education integration requirements
- **MOET Student Affairs Circular** (Thông tư 20/2021/TT-BGDĐT) - Student service standards
- **University Charter** (Điều lệ) - institutional governance document
- **Administrative Procedures Simplification** - 14 of 21 forms standardized to online submission

**Sector-Specific Compliance Requirements**:
- All policies must provide Vietnamese-language accuracy equivalent to English versions
- Government document authentication requirements for international processes
- Ministry of Education verification chain for degree program changes
- Vietnamese National Qualification Framework alignment requirements

**Non-Regulatory But Critical Constraints**:
- Vietnamese academic year structure (September start, two semesters)
- Government education calendar integration (public holidays, exam schedules)
- Vietnamese cultural sensitivity in student service communications
- Local banking and financial transaction requirements for fee payments

### Domain Expert Roles for Evaluation

**Vietnamese Higher Education Evaluation Team**:
- **MOET Compliance Inspector**: Evaluates Vietnamese regulatory compliance language accuracy
- **UIT Registrar**: Tests cohort-specific policy application accuracy
- **Academic Advisor**: Validates degree requirement interpretation across cohorts
- **Student Counselor**: Examines border case handling (transfer students, academic probation)
- **International Office**: Reviews cross-cultural communication clarity and cultural sensitivity
- **Financial Aid Officer**: Tests tuition calculation precision and scholarship eligibility accuracy
- **Vietnamese Language Undergraduate**: Validates natural Vietnamese administrative terminology and cultural appropriateness

**Testing Dataset Requirements**:
- Sample queries must include high-stakes academic decisions (graduation, transfer, international processes)
- Mixed Vietnamese-English queries reflecting real student communication patterns
- Temporal edge cases (student changing cohorts, mid-year policy changes)
- Financial calculation verification for both domestic and international students
- Cross-cultural interpretation challenges for international student populations

### Research Sources
- [Vietnamese Digital Education Policy 2025](https://files.eric.ed.gov/fulltext/EJ1427316.pdf) - MOET digital transformation requirements
- [UIT Student Affairs Regulations](https://ctsv.uit.edu.vn/quy-che-quy-dinh) - Vietnamese administrative procedures
- [VinUniversity Policy Variations by Cohort 2025](https://policy.vinuni.edu.vn/all-policies/academic-regulations-for-full-time-undergraduate-programs/) - Current cohort-specific policy examples
- [World Bank Higher Education Analysis](https://documents1.worldbank.org/curated/en/347431588175259657/pdf/Improving-the-Performance-of-Higher-Education-in-Vietnam-Strategic-Priorities-and-Policy-Options.pdf) - Regulatory coherence challenges
- [OECD Education Vietnam Profile](https://gpseducation.oecd.org/CountryProfile?primaryCountry=VNM) - Vietnamese education governance structure