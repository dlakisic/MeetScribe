/**
 * Shared application state for the MeetScribe dashboard.
 */

const state = {
    selectedMeetingId: null,
    transcriptData: null,
    meetingData: null,
    meetings: [],
    pollTimers: new Map(),
};

export default state;
