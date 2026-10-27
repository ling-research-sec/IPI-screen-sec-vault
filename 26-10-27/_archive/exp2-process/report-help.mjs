import {Workbook} from '@oai/artifact-tool';console.log(Workbook.create().help('range.merge',{include:'index,examples,notes',maxChars:2400}).ndjson);
