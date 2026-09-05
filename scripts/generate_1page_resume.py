#!/usr/bin/env python3
"""
Generate a tailored 1-page PDF resume using the project's generator.
"""

import importlib
import os
from pathlib import Path
from src.core.models import JobPosting

def generate_resume():
    job_desc = """
    Urgent Opening for Technical lead - .Net C#, Angular, Sacramento, California, (Hybrid)
    Must have Skills - C#,.Net Framework & Angular & Python We are looking for 7 - 10 years of experience, Git / GitHub / Bitbucket knowledge, Web Development Languages and Tools , JavaScript / TypeScript , HTML / Angular , C# / .NET , Scripting Languages , Python / PyTest.
    """
    
    # Create a JobPosting instance
    job = JobPosting(
        id="manual-tailor-job-001",
        company="Confidential",
        title="Technical lead - .Net C#, Angular",
        url="http://example.com",
        description=job_desc
    )
    
    # Dynamically import the ResumeGenerator and SurgicalOptimizer
    _tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")
    _opt_mod = importlib.import_module("src.pipeline.3_tailoring.surgical_optimizer")
    ResumeGenerator = _tailor_mod.ResumeGenerator
    SurgicalOptimizer = _opt_mod.SurgicalOptimizer
    
    # Initialize generator with custom optimizer to ensure keywords are bolded
    optimizer = SurgicalOptimizer(
        bold_cap=0.90, max_bold_phrases=10,
        allow_jd_tech_bold=True, allow_anchor_bold=False, bold_impact_only=False
    )
    generator = ResumeGenerator(optimizer=optimizer)
    
    # Generate artifacts with target_pages=1
    print("Generating 1-page PDF resume...")
    artifacts = generator.generate(job, target_pages=1)
    
    print("\nSuccess!")
    print(f"Generated PDF saved to: {artifacts.resume_pdf_path}")
    print(f"Generated Markdown saved to: {artifacts.resume_json_path}")
    
    # Optional: copy it to the root output/ directory for easy access
    output_pdf = Path("output") / "Alex_Rivera_Resume.pdf"
    if not output_pdf.parent.exists():
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        
    try:
        import shutil
        shutil.copy2(artifacts.resume_pdf_path, output_pdf)
        print(f"Copied PDF to root: {output_pdf.absolute()}")
    except Exception as e:
        print(f"Could not copy to output/: {e}")

if __name__ == "__main__":
    generate_resume()
