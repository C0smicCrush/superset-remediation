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
import injectCustomCss from 'src/dashboard/util/injectCustomCss';

test('injects valid CSS into a style element', () => {
  const remove = injectCustomCss('body { background: red; }');
  const style = document.querySelector('.CssEditor-css') as HTMLStyleElement;
  expect(style).toBeTruthy();
  expect(style.textContent).toBe('body { background: red; }');
  remove();
});

test('does not create sibling HTML elements from style breakout payload', () => {
  const payload = '</style><img src=x onerror=alert(1)>';
  const remove = injectCustomCss(payload);

  const imgs = document.head.querySelectorAll('img');
  expect(imgs.length).toBe(0);

  const style = document.querySelector('.CssEditor-css') as HTMLStyleElement;
  expect(style.textContent).toBe(payload);
  expect(style.childElementCount).toBe(0);
  remove();
});

test('does not execute script tags injected via style breakout', () => {
  const payload = '</style><script>window.__xss=true</script><style>';
  const remove = injectCustomCss(payload);

  expect((window as unknown as Record<string, unknown>).__xss).toBeUndefined();

  const scripts = document.head.querySelectorAll('script');
  expect(scripts.length).toBe(0);
  remove();
});

test('replaces CSS content on subsequent calls', () => {
  const remove1 = injectCustomCss('body { color: blue; }');
  const style = document.querySelector('.CssEditor-css') as HTMLStyleElement;
  expect(style.textContent).toBe('body { color: blue; }');

  injectCustomCss('body { color: green; }');
  expect(style.textContent).toBe('body { color: green; }');
  remove1();
});
