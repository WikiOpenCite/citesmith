CREATE TABLE `Migration` (
  `Name` varchar(64) UNIQUE PRIMARY KEY NOT NULL
);

CREATE TABLE `Worker` (
  `WorkerId` integer UNIQUE PRIMARY KEY NOT NULL AUTO_INCREMENT,
  `Name` varchar(255) NOT NULL
);

CREATE TABLE `Wiki` (
  `Name` varchar(64) UNIQUE PRIMARY KEY NOT NULL
);

CREATE TABLE `Dump` (
  `Wiki` varchar(64) NOT NULL,
  `Date` varchar(10) NOT NULL,
  `ReadyForCombining` bool DEFAULT false,
  `ProcessingComplete` bool DEFAULT false,
  PRIMARY KEY (`Wiki`, `Date`)
);

CREATE TABLE `File` (
  `FileId` integer UNIQUE PRIMARY KEY NOT NULL AUTO_INCREMENT,
  `Path` varchar(255) UNIQUE NOT NULL,
  `Complete` bool DEFAULT false,
  `Worker` integer NOT NULL,
  `DumpWiki` varchar(64) NOT NULL,
  `DumpDate` varchar(10) NOT NULL
);

ALTER TABLE `Dump` ADD FOREIGN KEY (`Wiki`) REFERENCES `Wiki` (`Name`);

ALTER TABLE `File` ADD FOREIGN KEY (`Worker`) REFERENCES `Worker` (`WorkerId`);

ALTER TABLE `File` ADD FOREIGN KEY (`DumpWiki`, `DumpDate`) REFERENCES `Dump` (`Wiki`, `Date`);