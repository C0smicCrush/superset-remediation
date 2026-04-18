/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

/**
 * Regression guard for the `follow-redirects` SSRF / cross-origin
 * header-leak advisory family:
 *
 *   - GHSA-cxjh-pqwp-8mfp: SSRF via `Proxy-Authorization` header leak on
 *     cross-origin redirect. Patched in `follow-redirects@1.15.4`.
 *   - GHSA-r4q5-vmmm-2653: follow-redirects leaks custom authentication
 *     headers (e.g. `X-API-Key`, `X-Auth-Token`) to cross-domain redirect
 *     targets. Affects `<= 1.15.11`, patched in `follow-redirects@1.16.0`.
 *
 * `follow-redirects` is pinned in `superset-frontend/package.json`
 * `overrides` to keep its resolved version at or above the patched
 * floor. This test asserts that the lockfile still reflects that pin so
 * the advisory cannot silently regress (e.g. if the override is dropped
 * or a transitive dep re-introduces a vulnerable range).
 */
import { readFileSync } from 'fs';
import { join } from 'path';

const PATCHED_FLOOR = '1.16.0';

type LockfileNode = {
  version?: string;
};

type Lockfile = {
  packages?: Record<string, LockfileNode>;
};

function parseSemver(version: string): [number, number, number] {
  const match = /^(\d+)\.(\d+)\.(\d+)/.exec(version);
  if (!match) {
    throw new Error(`Unparseable semver: ${version}`);
  }
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function gte(a: string, b: string): boolean {
  const [aMajor, aMinor, aPatch] = parseSemver(a);
  const [bMajor, bMinor, bPatch] = parseSemver(b);
  if (aMajor !== bMajor) return aMajor > bMajor;
  if (aMinor !== bMinor) return aMinor > bMinor;
  return aPatch >= bPatch;
}

test('follow-redirects is pinned to a patched version in the lockfile', () => {
  const lockfilePath = join(__dirname, '..', '..', 'package-lock.json');
  const lockfile: Lockfile = JSON.parse(readFileSync(lockfilePath, 'utf8'));
  const packages = lockfile.packages ?? {};

  const followRedirectsEntries = Object.entries(packages).filter(
    ([key, node]) =>
      /(^|\/)node_modules\/follow-redirects$/.test(key) &&
      typeof node.version === 'string',
  );

  // Sanity check: the dependency is actually present in the graph we
  // are guarding. If this ever becomes zero, the test needs to be
  // revisited (the advisory surface has changed) rather than silently
  // passing.
  expect(followRedirectsEntries.length).toBeGreaterThan(0);

  for (const [key, node] of followRedirectsEntries) {
    expect({
      package: key,
      version: node.version,
    }).toEqual({
      package: key,
      version: expect.stringMatching(/^\d+\.\d+\.\d+/),
    });
    expect(gte(node.version as string, PATCHED_FLOOR)).toBe(true);
  }
});
