# Controlled Multi-Commit Benchmark Plan

This benchmark contains 20 prospective application-level commits created
for evaluating change-aware predictive test selection.

Rules:

1. Each evaluated commit must modify `main.py`.
2. Test files will remain unchanged so the application-test inventory remains fixed.
3. Each commit must preserve the existing API contract.
4. The complete application suite must pass after every commit.
5. All 20 scenarios are defined before the comparative experiment is executed.
6. Commits will not be removed because of poor selector performance.
7. Mutation testing is evaluated separately.
8. These commits are controlled benchmark changes, not naturally occurring historical production commits.

Planned scenarios:

- C01 Health response API version
- C02 Response-time observability header
- C03 Request-ID normalization
- C04 Reset response error-injection state
- C05 Seed response requested count
- C06 Error-injection status metadata
- C07 Pagination has-next metadata
- C08 Pagination has-previous metadata
- C09 Pagination returned-count metadata
- C10 User post-count metadata
- C11 Stable ordering of user posts
- C12 Create-post audit logging
- C13 Update-post audit logging
- C14 Delete-post audit logging
- C15 Create-post input normalization
- C16 Update-post input normalization
- C17 Correct update-post 404 detail
- C18 Slow-response delay metadata
- C19 Large-payload generated-count metadata
- C20 Database total-record metric
