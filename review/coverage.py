from dataclasses import dataclass

from driving.arrivals import Arrival
from onboard.announcements import SpeechRecord
from onboard.commitments import Commitment


@dataclass(frozen=True)
class CoverageEntry:
    commitment: Commitment
    speech: SpeechRecord
    arrival: Arrival | None


def match_coverage(commitments, speeches, arrivals):
    by_speech = {speech.id: speech for speech in speeches}
    by_arrival = {arrival.id: arrival for arrival in arrivals}
    entries = []
    for commitment in commitments:
        speech = by_speech[commitment.speech_id]
        if (speech.trip, speech.occurrence, speech.station) != commitment.key:
            raise RuntimeError('The commitment and its speech disagree on the stop call')
        if speech.request != commitment.request:
            raise RuntimeError('The commitment and its speech disagree on the request')
        arrival = None
        if commitment.arrival_id is not None:
            arrival = by_arrival[commitment.arrival_id]
            if arrival.key != commitment.key:
                raise RuntimeError('The commitment was linked to a different stop call')
        entries.append(CoverageEntry(commitment, speech, arrival))
    return entries
