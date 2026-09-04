"""Career Knowledge Graph Builder.

Constructs a rich, multi-layer NetworkX DiGraph capturing:
- Candidate, Companies, Roles, and Projects
- STAR+R stories with linked Actions, Results, and Reflections
- Ontological Tech Categories & Taxonomies
- Architectural Design Patterns (CQRS, Event-Driven, Dead Letter Queues, etc.)
- Quantitative Impact Metrics and Competencies
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional, Set
import networkx as nx


logger = logging.getLogger(__name__)

TECH_TAXONOMY: Dict[str, str] = {
    # 1. Streaming & Distributed Messaging
    "Kafka": "EventStreaming",
    "Apache Kafka": "EventStreaming",
    "Amazon MSK": "EventStreaming",
    "AWS MSK": "EventStreaming",
    "SQS": "DistributedMessaging",
    "AWS SQS": "DistributedMessaging",
    "SNS": "DistributedMessaging",
    "AWS SNS": "DistributedMessaging",
    "EventBridge": "EventStreaming",
    "AWS EventBridge": "EventStreaming",
    "RabbitMQ": "DistributedMessaging",
    "Celery": "DistributedMessaging",
    "NATS": "DistributedMessaging",
    "ZeroMQ": "DistributedMessaging",
    "Apache Pulsar": "EventStreaming",
    "Kinesis": "EventStreaming",
    "AWS Kinesis": "EventStreaming",
    "ActiveMQ": "DistributedMessaging",

    # 2. Cloud Infrastructure & Serverless
    "AWS": "CloudInfrastructure",
    "AWS ECS": "CloudInfrastructure",
    "AWS ECS Fargate": "CloudInfrastructure",
    "ECS Fargate": "CloudInfrastructure",
    "AWS Lambda": "ServerlessCompute",
    "Lambda": "ServerlessCompute",
    "AWS Fargate": "CloudInfrastructure",
    "AWS EKS": "ContainerOrchestration",
    "AWS S3": "CloudInfrastructure",
    "S3": "CloudInfrastructure",
    "AWS API Gateway": "APITechnologies",
    "API Gateway": "APITechnologies",
    "AWS CloudFront": "CloudInfrastructure",
    "AWS Route53": "CloudInfrastructure",
    "AWS Step Functions": "ServerlessCompute",
    "AWS AppSync": "APITechnologies",
    "AWS IAM": "SecurityAndAuth",
    "AWS Secrets Manager": "SecurityAndAuth",
    "Azure": "CloudInfrastructure",
    "Azure AKS": "ContainerOrchestration",
    "Azure Functions": "ServerlessCompute",
    "Azure Service Bus": "DistributedMessaging",
    "Azure CosmosDB": "NoSQLDatabase",
    "Azure App Service": "CloudInfrastructure",
    "GCP": "CloudInfrastructure",
    "Google Cloud": "CloudInfrastructure",
    "Google Cloud Run": "ServerlessCompute",
    "GCP Cloud Run": "ServerlessCompute",
    "GKE": "ContainerOrchestration",
    "Google Kubernetes Engine": "ContainerOrchestration",
    "GCP Pub/Sub": "EventStreaming",
    "Google BigQuery": "DataWarehouse",

    # 3. Data & Storage
    "DynamoDB": "NoSQLDatabase",
    "AWS DynamoDB": "NoSQLDatabase",
    "MongoDB": "NoSQLDatabase",
    "Cassandra": "NoSQLDatabase",
    "Couchbase": "NoSQLDatabase",
    "Redis": "DistributedCaching",
    "Redis Cluster": "DistributedCaching",
    "Memcached": "DistributedCaching",
    "PostgreSQL": "RelationalDatabase",
    "Postgres": "RelationalDatabase",
    "SQL Server": "RelationalDatabase",
    "MS SQL Server": "RelationalDatabase",
    "T-SQL": "RelationalDatabase",
    "MySQL": "RelationalDatabase",
    "MariaDB": "RelationalDatabase",
    "Oracle": "RelationalDatabase",
    "SQLite": "RelationalDatabase",
    "SQL": "RelationalDatabase",
    "Snowflake": "DataWarehouse",
    "BigQuery": "DataWarehouse",
    "Databricks": "DataWarehouse",
    "Apache Spark": "DataWarehouse",
    "LanceDB": "VectorDatabase",
    "Milvus": "VectorDatabase",
    "Pinecone": "VectorDatabase",
    "Qdrant": "VectorDatabase",
    "ChromaDB": "VectorDatabase",
    "Elasticsearch": "SearchAndAnalytics",
    "OpenSearch": "SearchAndAnalytics",

    # 4. Languages & Runtimes
    "C#": "Languages",
    "C# 12": "Languages",
    "C# 10": "Languages",
    "Python": "Languages",
    "Python 3": "Languages",
    "TypeScript": "Languages",
    "JavaScript": "Languages",
    "Go": "Languages",
    "Golang": "Languages",
    "Rust": "Languages",
    "Java": "Languages",
    "VB.NET": "Languages",
    "C++": "Languages",
    "Bash": "Languages",
    "PowerShell": "Languages",
    "SQL": "Languages",

    # 5. Backend & Frontend Frameworks
    "ASP.NET Core": "BackendFrameworks",
    "ASP.NET": "BackendFrameworks",
    ".NET Core": "BackendFrameworks",
    ".NET 8": "BackendFrameworks",
    ".NET 9": "BackendFrameworks",
    ".NET 6": "BackendFrameworks",
    ".NET": "BackendFrameworks",
    "FastAPI": "BackendFrameworks",
    "Django": "BackendFrameworks",
    "Flask": "BackendFrameworks",
    "Spring Boot": "BackendFrameworks",
    "Node.js": "BackendFrameworks",
    "Express.js": "BackendFrameworks",
    "NestJS": "BackendFrameworks",
    "GraphQL": "APITechnologies",
    "REST": "APITechnologies",
    "RESTful APIs": "APITechnologies",
    "gRPC": "APITechnologies",
    "Protobuf": "APITechnologies",
    "WebSockets": "APITechnologies",
    "SignalR": "APITechnologies",
    "Angular": "FrontendFrameworks",
    "Angular 18": "FrontendFrameworks",
    "React": "FrontendFrameworks",
    "React.js": "FrontendFrameworks",
    "Next.js": "FrontendFrameworks",
    "Vue.js": "FrontendFrameworks",
    "RxJS": "FrontendFrameworks",
    "NgRx": "FrontendFrameworks",
    "Redux": "FrontendFrameworks",
    "Tailwind CSS": "FrontendFrameworks",

    # 6. DevOps, IaC & CI/CD
    "Docker": "DevOpsAndContainers",
    "Docker Compose": "DevOpsAndContainers",
    "Kubernetes": "ContainerOrchestration",
    "K8s": "ContainerOrchestration",
    "Helm": "ContainerOrchestration",
    "Istio": "ServiceMesh",
    "Terraform": "InfrastructureAsCode",
    "OpenTofu": "InfrastructureAsCode",
    "AWS CDK": "InfrastructureAsCode",
    "CloudFormation": "InfrastructureAsCode",
    "Pulumi": "InfrastructureAsCode",
    "Ansible": "DevOpsAndContainers",
    "GitHub Actions": "CICD",
    "GitLab CI": "CICD",
    "ArgoCD": "CICD",
    "Jenkins": "CICD",
    "CircleCI": "CICD",
    "Git": "CICD",
    "CI/CD": "CICD",

    # 7. Observability, Profiling & Incident Management
    "Dynatrace": "Observability",
    "Datadog": "Observability",
    "Prometheus": "Observability",
    "Grafana": "Observability",
    "Splunk": "Observability",
    "OpenTelemetry": "Observability",
    "OTel": "Observability",
    "Jaeger": "Observability",
    "AWS CloudWatch": "Observability",
    "CloudWatch": "Observability",
    "AWS X-Ray": "Observability",
    "WinDbg": "PerformanceProfiling",
    "dotnet-counters": "PerformanceProfiling",
    "dotnet-dump": "PerformanceProfiling",
    "dotnet-trace": "PerformanceProfiling",
    "PerfView": "PerformanceProfiling",
    "PagerDuty": "IncidentManagement",
    "Opsgenie": "IncidentManagement",
    "Synthetic Monitoring": "Observability",

    # 8. Generative AI & Orchestration
    "Amazon Bedrock": "GenerativeAI",
    "Bedrock": "GenerativeAI",
    "Claude Sonnet": "GenerativeAI",
    "Claude 3.5 Sonnet": "GenerativeAI",
    "OpenAI": "GenerativeAI",
    "GPT-4o": "GenerativeAI",
    "LangChain": "AIOrchestration",
    "LangGraph": "AIOrchestration",
    "LlamaIndex": "AIOrchestration",
    "GraphRAG": "GenerativeAI",
    "Vector RAG": "GenerativeAI",
    "Semantic Kernel": "AIOrchestration",
    "Prompt Guardrails": "AIGuardrails",
    "Intent-to-API Routing": "AIOrchestration",

    # 9. Security, Auth & Testing
    "OAuth2": "SecurityAndAuth",
    "OIDC": "SecurityAndAuth",
    "OAuth2/OIDC": "SecurityAndAuth",
    "JWT": "SecurityAndAuth",
    "mTLS": "SecurityAndAuth",
    "Keycloak": "SecurityAndAuth",
    "Playwright": "TestingAutomation",
    "Cypress": "TestingAutomation",
    "Selenium": "TestingAutomation",
    "xUnit": "TestingAutomation",
    "NUnit": "TestingAutomation",
    "MSTest": "TestingAutomation",
    "Moq": "TestingAutomation",
    "PyTest": "TestingAutomation",
    "TDD": "EngineeringMethodology",
    "DDD": "EngineeringMethodology",
    "Domain-Driven Design": "EngineeringMethodology",
    "Event Sourcing": "EngineeringMethodology",
}

ARCHITECTURAL_PATTERNS: Dict[str, str] = {
    "Event-Driven Architecture": "ArchitectureStyle",
    "Event-Driven": "ArchitectureStyle",
    "EDA": "ArchitectureStyle",
    "Microservices": "ArchitectureStyle",
    "Microservices Architecture": "ArchitectureStyle",
    "CQRS": "DataPattern",
    "Command Query Responsibility Segregation": "DataPattern",
    "Dead Letter Queue": "ReliabilityPattern",
    "Dead Letter Queues": "ReliabilityPattern",
    "DLQ": "ReliabilityPattern",
    "Idempotency": "ReliabilityPattern",
    "Idempotent Consumer": "ReliabilityPattern",
    "Circuit Breaker": "ResiliencePattern",
    "Bulkhead": "ResiliencePattern",
    "Rate Limiting": "ResiliencePattern",
    "Single-Table Design": "DataPattern",
    "Single-Table": "DataPattern",
    "Outbox Pattern": "DataPattern",
    "Transactional Outbox": "DataPattern",
    "Saga Pattern": "DataPattern",
    "Change Data Capture": "DataPattern",
    "CDC": "DataPattern",
    "Zero-Downtime Migration": "MigrationPattern",
    "Strangler Fig": "MigrationPattern",
    "Strangler Fig Pattern": "MigrationPattern",
    "Thread-Lock Profiling": "PerformancePattern",
    "Prompt Guardrails": "AIPattern",
    "Intent-to-API Routing": "AIPattern",
    "Synthetic Monitoring": "ObservabilityPattern",
    "Distributed Caching": "PerformancePattern",
    "Schema Governance": "GovernancePattern",
    "Asynchronous Decoupling": "ArchitectureStyle",
    "Zero-Trust Architecture": "SecurityPattern",
}

SYNONYM_MAP: Dict[str, str] = {
    "k8s": "Kubernetes",
    "postgres": "PostgreSQL",
    "eda": "Event-Driven Architecture",
    "dlq": "Dead Letter Queues",
    "oidc": "OAuth2/OIDC",
    "opentofu": "Terraform",
    "msk": "Amazon MSK",
    "ecs": "AWS ECS Fargate",
    "bedrock": "Amazon Bedrock",
    "otel": "OpenTelemetry",
    "golang": "Go",
    "csharp": "C#",
    "dotnet": ".NET",
    "aspnet": "ASP.NET Core",
    "ts": "TypeScript",
    "js": "JavaScript",
    "es": "Elasticsearch",
}

MACRO_DOMAINS: Dict[str, List[str]] = {
    "DistributedSystemsAndMessaging": ["EventStreaming", "DistributedMessaging", "APITechnologies", "ServiceMesh"],
    "CloudAndInfrastructure": ["CloudInfrastructure", "ServerlessCompute", "ContainerOrchestration", "InfrastructureAsCode", "CICD", "DevOpsAndContainers"],
    "DataEngineeringAndStorage": ["RelationalDatabase", "NoSQLDatabase", "VectorDatabase", "DataWarehouse", "DistributedCaching", "SearchAndAnalytics"],
    "GenerativeAIAndOrchestration": ["GenerativeAI", "AIOrchestration", "AIGuardrails", "AIPattern"],
    "ObservabilityAndReliability": ["Observability", "PerformanceProfiling", "IncidentManagement", "ObservabilityPattern", "ReliabilityPattern", "ResiliencePattern", "PerformancePattern"],
    "ApplicationDevelopment": ["Languages", "BackendFrameworks", "FrontendFrameworks", "TestingAutomation", "SecurityAndAuth", "EngineeringMethodology", "ArchitectureStyle", "DataPattern", "MigrationPattern", "GovernancePattern", "SecurityPattern"],
}

COMPETENCY_DIMENSIONS: Dict[str, List[str]] = {
    "SystemResilience": ["Circuit Breaker", "Bulkhead", "Dead Letter Queues", "Idempotency", "WinDbg", "Thread-Lock Profiling", "99.99%", "99.95%"],
    "OperationalExcellence": ["Dynatrace", "OpenTelemetry", "Splunk", "Synthetic Monitoring", "80% alert drop", "20 engineering hours monthly"],
    "CostOptimization": ["AWS ECS Fargate", "40%", "cost reduction", "caching", "SQL Server optimization", "70%"],
    "EnterpriseGovernance": ["Kafka", "Schema Governance", "standards", "Avro", "5 teams", "100% adoption"],
    "EngineeringVelocity": ["one-command", "local dev", "sub-15 minutes", "CI/CD", "GitHub Actions", "Docker Compose", "TDD"],
}


# Regex for registered tech terms
TECH_NAMES_PATTERN = "|".join(re.escape(k) for k in sorted(TECH_TAXONOMY.keys(), key=len, reverse=True))
TECH_REGEX = re.compile(rf"(?:^|[\s,.;:!?/()\[\]])({TECH_NAMES_PATTERN})(?=[,.;:!?/\s()\[\]]|$)", re.IGNORECASE)

# Regex for registered architectural patterns
PATTERN_NAMES_PATTERN = "|".join(re.escape(k) for k in sorted(ARCHITECTURAL_PATTERNS.keys(), key=len, reverse=True))
PATTERN_REGEX = re.compile(rf"(?:^|[\s,.;:!?/()\[\]])({PATTERN_NAMES_PATTERN})(?=[,.;:!?/\s()\[\]]|$)", re.IGNORECASE)

CALENDAR_YEAR_PATTERN = re.compile(r"^(?:19\d\d|20[0-4]\d)$")

STRICT_METRIC_REGEX = re.compile(
    r"("
    r"\d+(?:\.\d+)?%\s*(?:uptime|latency|reduction|increase|improvement|boost|accuracy|drop)?"
    r"|\$\s*\d+(?:\.\d+)?(?:k|K|M|B|million|thousand)?(?:\s*(?:annually|yearly|spend|cost|budget|saved))?"
    r"|\b\d+(?:\.\d+)?\s*(?:M\+|k\+|B\+|\+)\s*(?:daily events|events/day|uptime|latency|users|rps|qps|transactions|applications)?"
    r"|\b\d+(?:\.\d+)?\s*(?:M|k|K|B|million|billion)\s+(?:daily events|events/day|events|uptime|latency|users|rps|qps|transactions|applications)\b"
    r"|\b~?\d+\s*engineering hours(?:\s*monthly|\s*yearly)?"
    r"|\bsub-\d+[- ](?:second|minute|ms)\b"
    r"|\b\d+[- ]second\b"
    r"|\b(?:from\s+)?\d+s\s+to\s+<\d+s\b"
    r"|\b\d+\s*days\s*to\s*sub-\d+\s*minutes\b"
    r"|\b99\.9\d*%\b"
    r")",
    re.IGNORECASE,
)


def is_valid_metric(m_str: str) -> bool:
    """Strictly validate whether an extracted string is a true quantitative business outcome."""
    m = m_str.strip()
    if not m:
        return False
    if CALENDAR_YEAR_PATTERN.match(m):
        return False
    if m.isdigit():
        return False
    # Reject short artifacts like "4 m", "5 b", "2023040b"
    if re.match(r"^\d+\s*[a-zA-Z]$", m):
        return False
    if re.match(r"^[0-9a-fA-F]{6,}$", m):
        return False
    if not re.search(r"[%$\+]|(?:hour|sec|min|day|event|user|rps|qps|trans|up|drop|lat|cost|spend|million|billion)", m, re.IGNORECASE):
        return False
    return True



DATE_RANGE_REGEX = re.compile(
    r"\b(19\d\d|20\d\d)\b\s*[-–—to]+\s*\b(19\d\d|20\d\d|Present|Current)\b",
    re.IGNORECASE,
)


def extract_years(text: str) -> tuple[Optional[int], Optional[int], float]:
    """Extract start/end year and compute exponential recency score (e^-lambda*dt)."""
    current_year = 2026
    m = DATE_RANGE_REGEX.search(text)
    if m:
        sy = int(m.group(1))
        end_raw = m.group(2).lower()
        ey = current_year if ("present" in end_raw or "current" in end_raw) else int(m.group(2))
        recency = math.exp(-0.07 * max(0, current_year - ey))
        return sy, ey, float(max(0.2, min(1.0, recency)))
    single_m = re.findall(r"\b(20\d\d|19\d\d)\b", text)
    if single_m:
        ey = int(single_m[-1])
        sy = int(single_m[0])
        recency = math.exp(-0.07 * max(0, current_year - ey))
        return sy, ey, float(max(0.2, min(1.0, recency)))
    return None, None, 1.0


class CareerGraphBuilder:
    """Parses master resume markdown and builds an ontology-grounded NetworkX DiGraph."""

    def __init__(self) -> None:
        self.graph = nx.DiGraph()

    def build_from_text(self, resume_text: str) -> nx.DiGraph:
        """Parse structured markdown resume into a multi-layer NetworkX DiGraph."""
        self.graph.clear()
        lines = resume_text.splitlines()

        # Pre-seed tech category, pattern category, and macro-domain nodes
        for cat in set(TECH_TAXONOMY.values()):
            self.graph.add_node(cat, type="TechCategory", name=cat)
        for pcat in set(ARCHITECTURAL_PATTERNS.values()):
            self.graph.add_node(pcat, type="PatternCategory", name=pcat)
        for mdom in MACRO_DOMAINS:
            self.graph.add_node(mdom, type="MacroDomain", name=mdom)
        for comp_dim in COMPETENCY_DIMENSIONS:
            self.graph.add_node(comp_dim, type="CompetencyDimension", name=comp_dim)

        current_company = ""
        current_role = ""
        current_project = ""
        current_section = "general"
        current_start_year: Optional[int] = None
        current_end_year: Optional[int] = None
        current_recency: float = 1.0
        action_counter = 0

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Detect date metadata lines (e.g. *Jan 2023 – Jul 2025* or *2023 - Present*)
            if ("20" in line_str or "19" in line_str) and ("*" in line_str or "-" in line_str or "–" in line_str):
                sy, ey, rec = extract_years(line_str)
                if sy or ey:
                    current_start_year = sy
                    current_end_year = ey
                    current_recency = rec
                    if current_role and current_role in self.graph.nodes:
                        self.graph.nodes[current_role]["start_year"] = sy
                        self.graph.nodes[current_role]["end_year"] = ey
                        self.graph.nodes[current_role]["recency_score"] = rec

            # Detect main section headers
            if line_str.startswith("## "):
                sec_header = line_str.lstrip("#").strip().lower()
                if "summary" in sec_header:
                    current_section = "summary_variant"
                elif "experience" in sec_header or "story" in sec_header:
                    current_section = "production_story"
                elif "skill" in sec_header:
                    current_section = "skill_catalog"
                else:
                    current_section = "general"

            # Company & Role line: e.g. # Role — Company OR ### **Role** — *Company*
            clean_norm = line_str.replace("\u2014", " - ").replace("\u2013", " - ").replace("—", " - ").replace("–", " - ")
            clean_h = re.sub(r"^#+\s*", "", clean_norm).replace("*", "").strip()
            if " - " in clean_norm and (line_str.startswith("#") and not line_str.startswith("####")) and not clean_h.lower().startswith("story"):
                parts = re.split(r"\s*-\s*", clean_h, maxsplit=1)
                if len(parts) == 2 and parts[0].lower() not in ["projects", "experience", "education", "skills", "certifications"]:
                    current_role = parts[0].strip()
                    current_company = parts[1].strip()
                    sy, ey, rec = extract_years(line_str)
                    current_start_year = sy
                    current_end_year = ey
                    current_recency = rec
                    self.graph.add_node(current_company, type="Company", name=current_company)
                    self.graph.add_node(
                        current_role,
                        type="Role",
                        name=current_role,
                        company=current_company,
                        start_year=sy,
                        end_year=ey,
                        recency_score=rec,
                    )
                    self.graph.add_edge(current_company, current_role, relation="EMPLOYED")
                    current_project = ""

            # Project or Story line: e.g. ### Distributed Stream Pipeline or #### Story 4 — Modernization
            elif line_str.startswith("### ") or line_str.startswith("#### "):
                candidate_proj = re.sub(r"^#+\s*", "", line_str).replace("*", "").strip()
                if candidate_proj.lower() not in ["projects", "experience", "education", "skills", "certifications"]:
                    current_project = candidate_proj
                    is_story = current_project.lower().startswith("story") or line_str.startswith("####")
                    node_type = "STAR_Story" if is_story else "Project"
                    sec_type = "production_story" if (current_company or is_story) else current_section
                    self.graph.add_node(
                        current_project,
                        type=node_type,
                        name=current_project,
                        company=current_company,
                        role=current_role,
                        section_type=sec_type,
                        start_year=current_start_year,
                        end_year=current_end_year,
                        recency_score=current_recency,
                        bullets=[],
                    )
                    if current_company:
                        self.graph.add_edge(current_company, current_project, relation="CONTRIBUTED_TO")
                    if current_role:
                        self.graph.add_edge(current_role, current_project, relation="LED_STORY" if node_type == "STAR_Story" else "CONTRIBUTED_TO")

            # Bullet points: Granular STAR+R Decomposition
            elif line_str.startswith("- ") or line_str.startswith("* ") or line_str.startswith("• "):
                bullet = line_str.lstrip("*- •").strip()
                parent_node = current_project if current_project else current_role
                if parent_node and parent_node in self.graph.nodes:
                    self.graph.nodes[parent_node].setdefault("bullets", []).append(bullet)

                # Classify STAR sub-node type
                star_match = re.match(r"^\*?\*?(Situation|Task|Action|Result|Reflection|Tradeoff)\*?\*?:\s*(.*)", bullet, re.IGNORECASE)
                if star_match:
                    star_type = star_match.group(1).capitalize()
                    if star_type == "Tradeoff":
                        star_type = "Reflection"
                    core_text = star_match.group(2).strip()
                else:
                    core_text = bullet
                    lower_b = bullet.lower()
                    if any(k in lower_b for k in ["slashed", "reduced", "cutting", "improved", "saving", "achieved", "cut by"]):
                        star_type = "Result"
                    elif any(k in lower_b for k in ["diagnosed", "severe", "outage", "bottleneck", "fatigue", "overwhelming"]):
                        star_type = "Situation"
                    elif any(k in lower_b for k in ["established", "governance", "standards", "lessons", "adopted"]):
                        star_type = "Reflection"
                    else:
                        star_type = "Action"

                action_counter += 1
                subnode_name = f"{star_type} {action_counter}: {core_text[:40]}..."
                self.graph.add_node(
                    subnode_name,
                    type=star_type,
                    name=subnode_name,
                    bullet=bullet,
                    text=core_text,
                    parent=parent_node,
                    company=current_company,
                    role=current_role,
                    section_type=current_section,
                )
                if parent_node:
                    rel_name = f"HAS_{star_type.upper()}"
                    self.graph.add_edge(parent_node, subnode_name, relation=rel_name)
                    self.graph.add_edge(parent_node, subnode_name, relation="HAS_ACTION")

                # 1. Extract and link technologies (with alias resolution)
                tech_matches = TECH_REGEX.findall(bullet)
                found_techs: List[str] = []
                for raw_tech in tech_matches:
                    canonical_tech = next(
                        (k for k in TECH_TAXONOMY if k.lower() == raw_tech.lower()),
                        raw_tech.strip(),
                    )
                    cat = TECH_TAXONOMY.get(canonical_tech, "GeneralTechnology")
                    self.graph.add_node(
                        canonical_tech,
                        type="Technology",
                        name=canonical_tech,
                        category=cat,
                        aliases=[canonical_tech.lower()],
                    )
                    found_techs.append(canonical_tech)
                    self.graph.add_edge(subnode_name, canonical_tech, relation="USED_TECH")
                    if parent_node:
                        self.graph.add_edge(parent_node, canonical_tech, relation="USED_TECH")
                    if cat:
                        self.graph.add_edge(canonical_tech, cat, relation="BELONGS_TO_CATEGORY")

                # Check alias synonym map
                words = re.findall(r"\b[A-Za-z0-9+#\.-]+\b", bullet.lower())
                for w in words:
                    if w in SYNONYM_MAP:
                        canon = SYNONYM_MAP[w]
                        if canon in TECH_TAXONOMY:
                            cat = TECH_TAXONOMY[canon]
                            self.graph.add_node(canon, type="Technology", name=canon, category=cat, aliases=[canon.lower(), w])
                            if canon not in found_techs:
                                found_techs.append(canon)
                            self.graph.add_edge(subnode_name, canon, relation="USED_TECH")
                            if parent_node:
                                self.graph.add_edge(parent_node, canon, relation="USED_TECH")
                            if cat:
                                self.graph.add_edge(canon, cat, relation="BELONGS_TO_CATEGORY")
                        elif canon in ARCHITECTURAL_PATTERNS:
                            pcat = ARCHITECTURAL_PATTERNS[canon]
                            self.graph.add_node(canon, type="ArchitecturalPattern", name=canon, category=pcat)
                            self.graph.add_edge(subnode_name, canon, relation="IMPLEMENTS_PATTERN")
                            if parent_node:
                                self.graph.add_edge(parent_node, canon, relation="IMPLEMENTS_PATTERN")
                            if pcat:
                                self.graph.add_edge(canon, pcat, relation="BELONGS_TO_PATTERN_CATEGORY")

                # Link tech co-occurrences in the same action
                for i in range(len(found_techs)):
                    for j in range(i + 1, len(found_techs)):
                        t1, t2 = found_techs[i], found_techs[j]
                        if t1 != t2:
                            self.graph.add_edge(t1, t2, relation="CO_OCCURS_WITH")
                            self.graph.add_edge(t2, t1, relation="CO_OCCURS_WITH")

                # 2. Extract and link architectural patterns
                pattern_matches = PATTERN_REGEX.findall(bullet)
                for raw_pat in pattern_matches:
                    canonical_pat = next(
                        (k for k in ARCHITECTURAL_PATTERNS if k.lower() == raw_pat.lower()),
                        raw_pat.strip(),
                    )
                    pcat = ARCHITECTURAL_PATTERNS.get(canonical_pat, "ArchitecturePattern")
                    self.graph.add_node(
                        canonical_pat,
                        type="ArchitecturalPattern",
                        name=canonical_pat,
                        category=pcat,
                    )
                    self.graph.add_edge(subnode_name, canonical_pat, relation="IMPLEMENTS_PATTERN")
                    if parent_node:
                        self.graph.add_edge(parent_node, canonical_pat, relation="IMPLEMENTS_PATTERN")
                    if pcat:
                        self.graph.add_edge(canonical_pat, pcat, relation="BELONGS_TO_PATTERN_CATEGORY")

                # 3. Extract and link strictly validated quantitative impact metrics
                metric_matches = STRICT_METRIC_REGEX.findall(bullet)
                for metric in metric_matches:
                    m_clean = metric.strip()
                    if is_valid_metric(m_clean):
                        metric_node = f"metric_{m_clean}"
                        self.graph.add_node(
                            metric_node,
                            type="ImpactMetric",
                            value=m_clean,
                            bullet=bullet,
                        )
                        self.graph.add_edge(subnode_name, metric_node, relation="ACHIEVED_METRIC")
                        if parent_node:
                            self.graph.add_edge(parent_node, metric_node, relation="ACHIEVED_METRIC")

                # 4. Competency Dimension Grounding
                lower_b = bullet.lower()
                for c_dim, keywords in COMPETENCY_DIMENSIONS.items():
                    if any(kw.lower() in lower_b for kw in keywords):
                        self.graph.add_edge(subnode_name, c_dim, relation="HAS_COMPETENCY")
                        if parent_node:
                            self.graph.add_edge(parent_node, c_dim, relation="HAS_COMPETENCY")

        # Link active categories to MacroDomains
        for mdom, cats in MACRO_DOMAINS.items():
            for cat in cats:
                if self.graph.has_node(cat):
                    self.graph.add_edge(cat, mdom, relation="PART_OF_DOMAIN")

        # Prune unreferenced pre-seeded category/macro/competency nodes (0 in-degree and 0 out-degree)
        unused_nodes = [
            n for n, d in self.graph.nodes(data=True)
            if d.get("type") in ("TechCategory", "PatternCategory", "MacroDomain", "CompetencyDimension")
            and self.graph.in_degree(n) == 0 and self.graph.out_degree(n) == 0
        ]
        for u_node in unused_nodes:
            self.graph.remove_node(u_node)

        return self.graph



    def to_dict(self) -> Dict[str, Any]:
        """Serialize graph to dictionary."""
        return nx.node_link_data(self.graph)

    def from_dict(self, data: Dict[str, Any]) -> nx.DiGraph:
        """Deserialize graph from dictionary."""
        edges_key = "links" if "links" in data else "edges"
        try:
            self.graph = nx.node_link_graph(data, directed=True, edges=edges_key)
        except TypeError:
            self.graph = nx.node_link_graph(data, directed=True)
        return self.graph


