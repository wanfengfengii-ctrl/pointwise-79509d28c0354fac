from driving.arrivals import list_arrivals
from onboard.announcements import list_announcements
from onboard.commitments import list_commitments
from review.coverage import match_coverage
from review.summaries import build_summary
from transport import encode


def finalize_review(db, trip, revision):
    arrivals = list_arrivals(db, trip)
    commitments = list_commitments(db, trip)
    speeches = list_announcements(db, trip)
    coverage = match_coverage(commitments, speeches, arrivals)
    summary = build_summary(trip, revision, arrivals, coverage)
    db.execute('INSERT INTO reviews (trip, summary) VALUES (?, ?)', (trip, encode(summary.as_dict())))
    return summary
