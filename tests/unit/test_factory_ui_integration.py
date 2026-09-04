"""Unit tests verifying factory UI integration in Mission Control templates."""

from pathlib import Path
import pytest


def test_base_template_loads_pixijs_and_no_office3d():
    """base.html should load PixiJS and not load deprecated office3d scripts."""
    base_html = Path("web/templates/base.html").read_text(encoding="utf-8")
    
    # Assert PixiJS CDN is included
    assert "pixi.min.js" in base_html, "base.html must load PixiJS v7 runtime"
    
    # Assert office3d scripts are removed
    assert "/static/office3d/" not in base_html, "base.html must not load deprecated office3d scripts"


def test_tab_subagents_contains_factory_dom():
    """tab_subagents.html must include factory canvas, panel-root, and overlay-root."""
    tab_html = Path("web/templates/partials/tab_subagents.html").read_text(encoding="utf-8")
    
    assert 'id="factory-canvas"' in tab_html, "tab_subagents.html must have #factory-canvas"
    assert 'id="panel-root"' in tab_html, "tab_subagents.html must have #panel-root"
    assert 'id="overlay-root"' in tab_html, "tab_subagents.html must have #overlay-root"
    assert 'id="office-3d-canvas"' not in tab_html, "tab_subagents.html should not have old office-3d-canvas"


def test_main_css_does_not_import_office3d():
    """main.css must not import office3d.css."""
    css = Path("web/css/main.css").read_text(encoding="utf-8")
    assert "office3d.css" not in css, "main.css should not import office3d.css"
