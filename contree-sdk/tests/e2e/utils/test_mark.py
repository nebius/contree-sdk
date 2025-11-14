async def test_mark(request):
    markers = {m.name for m in request.node.iter_markers()}
    assert "e2e" in markers, f"Test should have e2e marker, but has: {markers}"
