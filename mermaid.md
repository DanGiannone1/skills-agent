flowchart TD
    Start((START)) --> GetApproved[Get Approved Values]
    Start --> GetTarget[Get Target Employees]
    GetApproved --> GetData[Get Employee Data]
    GetTarget --> GetData
    
    subgraph Employee_1[Process Employee 1]
        E1_WD[Analyze WorkDay Data] --> E1_PH[Analyze Project History]
        E1_PH --> E1_RC[Review & Combine]
        E1_RC --> E1_SN[Send Notification]
    end
    
    subgraph Employee_2[Process Employee 2]
        E2_WD[Analyze WorkDay Data] --> E2_PH[Analyze Project History]
        E2_PH --> E2_RC[Review & Combine]
        E2_RC --> E2_SN[Send Notification]
    end
    
    subgraph Employee_N[Process Employee N]
        EN_WD[Analyze WorkDay Data] --> EN_PH[Analyze Project History]
        EN_PH --> EN_RC[Review & Combine]
        EN_RC --> EN_SN[Send Notification]
    end
    
    GetData --> Employee_1
    GetData --> Employee_2
    GetData --> Employee_N
    
    Employee_1 --> End((END))
    Employee_2 --> End
    Employee_N --> End