"use server";

import { submitFeedback, type FeedbackInput, type FeedbackResult } from "@/lib/data";

/**
 * Server action backing the public feedback form. Runs on the server so
 * API_URL stays server-side (POST /api/public/feedback); the client island
 * calls it from the submit handler and awaits the {ok, status} result.
 */
export async function submitFeedbackAction(input: FeedbackInput): Promise<FeedbackResult> {
  return submitFeedback(input);
}
