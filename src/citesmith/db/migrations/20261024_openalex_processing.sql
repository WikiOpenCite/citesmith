-- SPDX-FileCopyrightText: 2026 The University of St Andrews
-- SPDX-License-Identifier: GPL-3.0-or-later


CREATE TABLE `OpenAlexDump` (
  `Date` varchar(10) NOT NULL PRIMARY KEY,
  `ReadyForCombining` bool DEFAULT false,
  `ProcessingComplete` bool DEFAULT false
);

CREATE TABLE `OpenAlexFile` (
  `FileId` integer UNIQUE PRIMARY KEY NOT NULL AUTO_INCREMENT,
  `Path` varchar(255) UNIQUE NOT NULL,
  `Complete` bool DEFAULT false,
  `DumpDate` varchar(10) NOT NULL
);

ALTER TABLE `OpenAlexFile` ADD FOREIGN KEY (`DumpDate`) REFERENCES `OpenAlexDump` (`Date`);
