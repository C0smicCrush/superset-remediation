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
import exportPivotExcel from './downloadAsPivotExcel';

jest.mock('xlsx', () => ({
  utils: { table_to_book: jest.fn() },
  writeFile: jest.fn(),
}));

const mockTableToBook = utils.table_to_book as jest.Mock;
const mockWriteFile = writeFile as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  document.body.innerHTML = '';
});

test('exportPivotExcel exports the workbook when the table element exists', () => {
  const table = document.createElement('table');
  table.id = 'pivot-table';
  document.body.appendChild(table);

  const fakeBook = { SheetNames: [], Sheets: {} };
  mockTableToBook.mockReturnValue(fakeBook);

  exportPivotExcel('#pivot-table', 'report');

  expect(mockTableToBook).toHaveBeenCalledWith(table);
  expect(mockWriteFile).toHaveBeenCalledWith(fakeBook, 'report.xlsx');
});

test('exportPivotExcel does not call xlsx when no element matches the selector', () => {
  const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

  expect(() => exportPivotExcel('#missing-table', 'report')).not.toThrow();

  expect(mockTableToBook).not.toHaveBeenCalled();
  expect(mockWriteFile).not.toHaveBeenCalled();
  expect(errorSpy).toHaveBeenCalledWith(
    expect.stringContaining('#missing-table'),
  );

  errorSpy.mockRestore();
});
