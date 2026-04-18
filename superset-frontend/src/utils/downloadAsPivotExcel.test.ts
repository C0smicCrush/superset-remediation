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
import { utils, writeFile } from 'xlsx';
import { addWarningToast } from 'src/components/MessageToasts/actions';
import exportPivotExcel from './downloadAsPivotExcel';

jest.mock('xlsx', () => ({
  __esModule: true,
  utils: { table_to_book: jest.fn(() => ({ mock: 'workbook' })) },
  writeFile: jest.fn(),
}));

jest.mock('src/components/MessageToasts/actions', () => ({
  addWarningToast: jest.fn(),
}));

jest.mock('@apache-superset/core/translation', () => ({
  t: (str: string) => str,
}));

const mockTableToBook = utils.table_to_book as jest.Mock;
const mockWriteFile = writeFile as jest.Mock;
const mockAddWarningToast = addWarningToast as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  document.body.innerHTML = '';
});

test('fails gracefully and does not call xlsx when the selector matches nothing', () => {
  expect(() => exportPivotExcel('#does-not-exist', 'file')).not.toThrow();

  expect(mockTableToBook).not.toHaveBeenCalled();
  expect(mockWriteFile).not.toHaveBeenCalled();
  expect(mockAddWarningToast).toHaveBeenCalledTimes(1);
  expect(mockAddWarningToast.mock.calls[0][0]).toMatch(/pivot table/i);
});

test('fails gracefully when the matched element is not a table', () => {
  const div = document.createElement('div');
  div.id = 'not-a-table';
  document.body.appendChild(div);

  expect(() => exportPivotExcel('#not-a-table', 'file')).not.toThrow();

  expect(mockTableToBook).not.toHaveBeenCalled();
  expect(mockWriteFile).not.toHaveBeenCalled();
  expect(mockAddWarningToast).toHaveBeenCalledTimes(1);
});

test('exports the workbook when the selector resolves to a real table', () => {
  const table = document.createElement('table');
  table.id = 'pvt';
  const row = table.insertRow();
  row.insertCell().textContent = 'a';
  row.insertCell().textContent = 'b';
  document.body.appendChild(table);

  exportPivotExcel('#pvt', 'my-file');

  expect(mockTableToBook).toHaveBeenCalledTimes(1);
  expect(mockTableToBook).toHaveBeenCalledWith(table);
  expect(mockWriteFile).toHaveBeenCalledWith(
    { mock: 'workbook' },
    'my-file.xlsx',
  );
  expect(mockAddWarningToast).not.toHaveBeenCalled();
});
