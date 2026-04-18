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
  utils: { table_to_book: jest.fn() },
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

test('exportPivotExcel does not throw and warns when the selector matches no element', () => {
  // Cause xlsx.utils.table_to_book to reproduce the upstream TypeError if an
  // unguarded null ever reaches it. This asserts the guard in the utility is
  // the thing keeping the export path safe — not luck in a test environment.
  mockTableToBook.mockImplementation((table: unknown) => {
    if (table == null) {
      throw new TypeError("Cannot read properties of null (reading 'rows')");
    }
    return { SheetNames: [], Sheets: {} };
  });

  expect(() =>
    exportPivotExcel('#does-not-exist .pvtTable', 'my-export'),
  ).not.toThrow();

  expect(mockTableToBook).not.toHaveBeenCalled();
  expect(mockWriteFile).not.toHaveBeenCalled();
  expect(mockAddWarningToast).toHaveBeenCalledTimes(1);
});

test('exportPivotExcel downloads the workbook when the table element exists', () => {
  const table = document.createElement('table');
  table.className = 'pvtTable';
  const container = document.createElement('div');
  container.id = 'chart-id-1';
  container.appendChild(table);
  document.body.appendChild(container);

  const workbook = { SheetNames: ['Sheet1'], Sheets: { Sheet1: {} } };
  mockTableToBook.mockReturnValue(workbook);

  exportPivotExcel('#chart-id-1 .pvtTable', 'my-export');

  expect(mockTableToBook).toHaveBeenCalledTimes(1);
  expect(mockTableToBook).toHaveBeenCalledWith(table);
  expect(mockWriteFile).toHaveBeenCalledWith(workbook, 'my-export.xlsx');
  expect(mockAddWarningToast).not.toHaveBeenCalled();
});

test('exportPivotExcel warns when table_to_book throws unexpectedly', () => {
  const table = document.createElement('table');
  table.className = 'pvtTable';
  const container = document.createElement('div');
  container.id = 'chart-id-1';
  container.appendChild(table);
  document.body.appendChild(container);

  mockTableToBook.mockImplementation(() => {
    throw new Error('boom');
  });

  expect(() =>
    exportPivotExcel('#chart-id-1 .pvtTable', 'my-export'),
  ).not.toThrow();

  expect(mockWriteFile).not.toHaveBeenCalled();
  expect(mockAddWarningToast).toHaveBeenCalledTimes(1);
});
