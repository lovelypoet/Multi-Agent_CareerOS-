from app.integrations.remoteok import RemoteOKFetchError, parse_remoteok_response


def test_parses_remoteok_job_and_cleans_html_description():
    jobs = parse_remoteok_response(
        [
            {"legal": "Remote OK API attribution notice"},
            {
                "position": "AI Engineer",
                "company": "Example AI",
                "url": "https://remoteok.com/remote-jobs/123-ai-engineer",
                "tags": ["Python", "Machine Learning"],
                "description": "<p>Build <strong>AI</strong> systems.</p>",
            },
        ]
    )

    assert len(jobs) == 1
    assert jobs[0].title == "AI Engineer"
    assert jobs[0].company == "Example AI"
    assert jobs[0].skill_tags == ["Python", "Machine Learning"]
    assert jobs[0].description == "Build\nAI\nsystems."


def test_skips_job_urls_outside_remoteok():
    jobs = parse_remoteok_response(
        [
            {
                "position": "AI Engineer",
                "company": "Example AI",
                "url": "https://example.com/remote-jobs/123-ai-engineer",
                "tags": [],
                "description": "Description",
            }
        ]
    )

    assert jobs == []


def test_rejects_unexpected_feed_shape():
    try:
        parse_remoteok_response({"jobs": []})
    except RemoteOKFetchError:
        pass
    else:
        raise AssertionError("Unexpected feed shape should raise RemoteOKFetchError.")
