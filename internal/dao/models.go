package dao

import (
	"time"
)

// BaseModel handles the standard timestamps
type BaseModel struct {
	CreateTime int64     `gorm:"index;autoCreateTime:milli"`
	CreateDate time.Time `gorm:"index;autoCreateTime"`
	UpdateTime int64     `gorm:"index;autoUpdateTime:milli"`
	UpdateDate time.Time `gorm:"index;autoUpdateTime"`
}

// User Model
type User struct {
	ID          string `gorm:"primaryKey;type:varchar(32)"`
	AccessToken string `gorm:"index;type:varchar(255)"`
	Nickname    string `gorm:"index;type:varchar(100);not null"`
	Password    string `gorm:"index;type:varchar(255)"`
	Email       string `gorm:"uniqueIndex;type:varchar(255);not null"`
	Avatar      string `gorm:"type:text"`
	Language    string `gorm:"index;type:varchar(32);default:'English'"`
	Timezone    string `gorm:"index;type:varchar(64);default:'UTC+8\tAsia/Shanghai'"`
	IsActive    string `gorm:"index;type:varchar(1);not null;default:'1'"`
	IsSuperuser bool   `gorm:"index;default:false"`
	BaseModel
}

func (User) TableName() string {
	return "user"
}

// Tenant Model
type Tenant struct {
	ID        string `gorm:"primaryKey;type:varchar(32)"`
	Name      string `gorm:"index;type:varchar(100)"`
	PublicKey string `gorm:"index;type:varchar(255)"`
	LlmID     string `gorm:"index;type:varchar(128);not null"`
	EmbdID    string `gorm:"index;type:varchar(128);not null"`
	Status    string `gorm:"index;type:varchar(1);default:'1'"`
	BaseModel
}

func (Tenant) TableName() string {
	return "tenant"
}

// UserTenant Model
type UserTenant struct {
	ID       string `gorm:"primaryKey;type:varchar(32)"`
	UserID   string `gorm:"index;type:varchar(32);not null"`
	TenantID string `gorm:"index;type:varchar(32);not null"`
	Role     string `gorm:"index;type:varchar(32);not null"`
	Status   string `gorm:"index;type:varchar(1);default:'1'"`
	BaseModel
}

func (UserTenant) TableName() string {
	return "user_tenant"
}

// Document Model
type Document struct {
	ID          string  `gorm:"primaryKey;type:varchar(32)"`
	Thumbnail   string  `gorm:"type:text"`
	KbID        string  `gorm:"index;type:varchar(256);not null"`
	ParserID    string  `gorm:"index;type:varchar(32);not null"`
	SourceType  string  `gorm:"type:varchar(128);not null;default:'local'"`
	Type        string  `gorm:"type:varchar(32);not null"`
	CreatedBy   string  `gorm:"type:varchar(32);not null"`
	Name        string  `gorm:"type:varchar(255)"`
	Location    string  `gorm:"type:varchar(255)"`
	Size        int64   `gorm:"default:0"`
	TokenNum    int     `gorm:"default:0"`
	ChunkNum    int     `gorm:"default:0"`
	Progress    float64 `gorm:"default:0.0"`
	ProgressMsg string  `gorm:"type:text"`
	Status      string  `gorm:"index;type:varchar(1);default:'1'"`
	ContentHash string  `gorm:"index;type:varchar(64)"`
	BaseModel
}

func (Document) TableName() string {
	return "document"
}

// Knowledgebase Model
type Knowledgebase struct {
	ID                     string  `gorm:"primaryKey;type:varchar(32)"`
	Avatar                 string  `gorm:"type:text"`
	TenantID               string  `gorm:"index;type:varchar(32);not null"`
	Name                   string  `gorm:"index;type:varchar(128);not null"`
	Language               string  `gorm:"index;type:varchar(32);default:'English'"`
	Description            string  `gorm:"type:text"`
	EmbdID                 string  `gorm:"index;type:varchar(128);not null"`
	Permission             string  `gorm:"index;type:varchar(16);default:'me'"`
	CreatedBy              string  `gorm:"index;type:varchar(32);not null"`
	DocNum                 int     `gorm:"index;default:0"`
	TokenNum               int     `gorm:"index;default:0"`
	ChunkNum               int     `gorm:"index;default:0"`
	SimilarityThreshold    float64 `gorm:"index;default:0.2"`
	VectorSimilarityWeight float64 `gorm:"index;default:0.3"`
	ParserID               string  `gorm:"index;type:varchar(32);default:'naive'"`
	ParserConfig           string  `gorm:"type:text"`
	Status                 string  `gorm:"index;type:varchar(1);default:'1'"`

	// Advanced Indexing Flags
	GraphragTaskID        string     `gorm:"index;type:varchar(32)"`
	GraphragTaskFinishAt  *time.Time `gorm:"type:datetime"`
	RaptorTaskID          string     `gorm:"index;type:varchar(32)"`
	RaptorTaskFinishAt    *time.Time `gorm:"type:datetime"`
	MindmapTaskID         string     `gorm:"index;type:varchar(32)"`
	MindmapTaskFinishAt   *time.Time `gorm:"type:datetime"`

	BaseModel
}

func (Knowledgebase) TableName() string {
	return "knowledgebase"
}
