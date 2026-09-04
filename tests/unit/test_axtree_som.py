"""Unit tests for AXTree Perception Engine and Set-of-Marks (SoM) Annotator."""

import importlib
from unittest.mock import AsyncMock, MagicMock
import pytest

axtree_mod = importlib.import_module("src.pipeline.4_submission.axtree_parser")
AXNode = axtree_mod.AXNode
AXTreeParser = axtree_mod.AXTreeParser
inject_bid_attributes = axtree_mod.inject_bid_attributes
inject_bid_attributes_async = axtree_mod.inject_bid_attributes_async

som_mod = importlib.import_module("src.pipeline.4_submission.som_annotator")
SetOfMarksAnnotator = som_mod.SetOfMarksAnnotator


SAMPLE_AXTREE_SNAPSHOT = {
    "role": "WebArea",
    "name": "Workday Application",
    "children": [
        {"role": "heading", "name": "Personal Information"},
        {"role": "paragraph", "name": "Please enter your details below."},
        {"role": "textbox", "name": "Legal First Name", "value": "Jane"},
        {"role": "textbox", "name": "Legal Last Name", "value": ""},
        {
            "role": "combobox",
            "name": "Country",
            "value": "United States",
            "children": [
                {"role": "option", "name": "United States"},
                {"role": "option", "name": "Canada"},
                {"role": "option", "name": "United Kingdom"},
            ],
        },
        {"role": "checkbox", "name": "I agree to terms and conditions"},
        {"role": "radio", "name": "Full-time employment"},
        {"role": "link", "name": "Privacy Policy"},
        {"role": "file_upload", "name": "Resume / CV"},
        {
            "role": "group",
            "name": "Action Group",
            "children": [
                {"role": "button", "name": "Save and Continue"},
                {"role": "button", "name": "Cancel"},
            ],
        },
    ],
}


def test_axnode_dataclass_creation():
    """Verify AXNode model fields and defaults."""
    node = AXNode(
        bid=1,
        role="textbox",
        name="Email Address",
        value="jane@example.com",
        children_options=["Opt 1", "Opt 2"],
    )
    assert node.bid == 1
    assert node.role == "textbox"
    assert node.name == "Email Address"
    assert node.value == "jane@example.com"
    assert node.children_options == ["Opt 1", "Opt 2"]

    default_node = AXNode(bid=2, role="button", name="Submit")
    assert default_node.bid == 2
    assert default_node.value is None
    assert default_node.children_options is None


def test_axtree_parser_extracts_interactive_bids_and_prunes_noise():
    """Verify interactive role extraction while pruning headings and static text."""
    parser = AXTreeParser()
    nodes = parser.extract_interactive_bids(SAMPLE_AXTREE_SNAPSHOT)

    # 2 textboxes + 1 combobox + 1 checkbox + 1 radio + 1 link + 1 file_upload + 2 buttons = 9
    assert len(nodes) == 9

    # Check 1-based sequential BIDs
    bids = [n.bid for n in nodes]
    assert bids == list(range(1, 10))

    # Node 1: First Name textbox
    assert nodes[0].bid == 1
    assert nodes[0].role == "textbox"
    assert nodes[0].name == "Legal First Name"
    assert nodes[0].value == "Jane"

    # Node 3: Country combobox with options
    assert nodes[2].bid == 3
    assert nodes[2].role == "combobox"
    assert nodes[2].name == "Country"
    assert nodes[2].children_options == ["United States", "Canada", "United Kingdom"]

    # Node 4: Checkbox
    assert nodes[3].bid == 4
    assert nodes[3].role == "checkbox"
    assert nodes[3].name == "I agree to terms and conditions"

    # Node 5: Radio
    assert nodes[4].bid == 5
    assert nodes[4].role == "radio"
    assert nodes[4].name == "Full-time employment"

    # Node 6: Link
    assert nodes[5].bid == 6
    assert nodes[5].role == "link"
    assert nodes[5].name == "Privacy Policy"

    # Node 7: File Upload
    assert nodes[6].bid == 7
    assert nodes[6].role == "file_upload"
    assert nodes[6].name == "Resume / CV"

    # Node 8: Save and Continue button
    assert nodes[7].bid == 8
    assert nodes[7].role == "button"
    assert nodes[7].name == "Save and Continue"

    # Node 9: Cancel button
    assert nodes[8].bid == 9
    assert nodes[8].role == "button"
    assert nodes[8].name == "Cancel"


def test_axtree_parser_empty_and_malformed():
    """Verify parser handles empty or malformed snapshots gracefully."""
    parser = AXTreeParser()
    assert parser.extract_interactive_bids({}) == []
    assert parser.extract_interactive_bids({"role": "generic"}) == []
    assert parser.extract_interactive_bids({"role": "heading", "name": "Title"}) == []


def test_axtree_parser_case_insensitivity_and_aliases():
    """Verify role parsing handles uppercase and common interactive aliases."""
    parser = AXTreeParser()
    snapshot = {
        "role": "Root",
        "children": [
            {"role": "TEXTBOX", "name": "Upper Text"},
            {"role": "searchbox", "name": "Search"},
            {"role": "Switch", "name": "Enable Notifications"},
            {"role": "menuitem", "name": "Profile"},
        ],
    }
    nodes = parser.extract_interactive_bids(snapshot)
    assert len(nodes) == 4
    roles = [n.role for n in nodes]
    assert roles == ["textbox", "searchbox", "switch", "menuitem"]


def test_inject_bid_attributes_sync():
    """Verify inject_bid_attributes executes JS injection in synchronous Playwright page."""
    mock_page = MagicMock()
    mock_page.evaluate.return_value = 5

    count = inject_bid_attributes(mock_page)

    assert count == 5
    assert mock_page.evaluate.called
    js_arg = mock_page.evaluate.call_args[0][0]
    assert "data-bid" in js_arg


@pytest.mark.asyncio
async def test_inject_bid_attributes_async():
    """Verify inject_bid_attributes_async executes JS injection in async Playwright page."""
    mock_page = AsyncMock()
    mock_page.evaluate.return_value = 7

    count = await inject_bid_attributes_async(mock_page)

    assert count == 7
    assert mock_page.evaluate.called
    js_arg = mock_page.evaluate.call_args[0][0]
    assert "data-bid" in js_arg


def test_inject_bid_attributes_exception_handling():
    """Verify inject_bid_attributes returns 0 and logs error if evaluation fails."""
    mock_page = MagicMock()
    mock_page.evaluate.side_effect = Exception("Page crashed")

    count = inject_bid_attributes(mock_page)
    assert count == 0


def test_som_annotator_format_prompt_representation():
    """Verify format_prompt_representation outputs compact markdown/text representation."""
    parser = AXTreeParser()
    nodes = parser.extract_interactive_bids(SAMPLE_AXTREE_SNAPSHOT)
    annotator = SetOfMarksAnnotator()

    representation = annotator.format_prompt_representation(nodes)

    assert '[1] <textbox> "Legal First Name"' in representation
    assert '[3] <combobox> "Country" (Options: United States, Canada, United Kingdom)' in representation
    assert '[4] <checkbox> "I agree to terms and conditions"' in representation
    assert '[8] <button> "Save and Continue"' in representation

    # Compactness check: Representation of standard form must be well under 600 tokens (< 2400 chars)
    assert len(representation) < 1000


def test_som_annotator_format_with_values():
    """Verify representation includes current value when include_values=True or present."""
    nodes = [
        AXNode(bid=1, role="textbox", name="First Name", value="Jane"),
        AXNode(bid=2, role="textbox", name="Last Name", value=None),
        AXNode(bid=3, role="combobox", name="State", value="NY", children_options=["NY", "CA"]),
    ]
    annotator = SetOfMarksAnnotator()
    rep = annotator.format_prompt_representation(nodes, include_values=True)

    assert '[1] <textbox> "First Name" [Value: "Jane"]' in rep
    assert '[2] <textbox> "Last Name"' in rep
    assert '[3] <combobox> "State" [Value: "NY"] (Options: NY, CA)' in rep


def test_som_annotator_large_tree_compactness():
    """Verify prompt representation scales compactly for large forms."""
    nodes = [
        AXNode(
            bid=i,
            role="textbox" if i % 2 == 0 else "button",
            name=f"Field or Action {i}",
            value=f"Value {i}" if i % 2 == 0 else None,
        )
        for i in range(1, 41)
    ]
    annotator = SetOfMarksAnnotator()
    rep = annotator.format_prompt_representation(nodes, include_values=True)

    # 40 nodes must stay under 600 tokens (~2400 characters)
    assert len(rep) < 2400
    assert rep.count("\n") == 39
