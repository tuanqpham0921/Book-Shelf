import VersionDropdown from '@/components/subheader/VersionDropdown';

const SubHeader = ({ activeView, setActiveView }) => {
    // This is a subheader for specific pages like the portfolio page
    // useful for mobile and formatting pages (chat, about pages, tips, version dropdown, etc)

    const handleViewChange = (view) => {
        setActiveView(view);
    };

    return (
        <div className="flex flex-row items-center w-full gap-8">

            {[['chat', 'Chat'], ['bookshelf', 'About'], ['airglider', 'Airglider'], ['planjane', 'PlanJane']].map(([view, label]) => (
                <button
                    key={view}
                    onClick={() => handleViewChange(view)}
                    className={`underline-animated underline-button ${activeView === view ? 'active' : ''}`}
                >
                    {label}
                </button>
            ))}

            {/* <button
                onClick={() => handleViewChange('review')}
                className={`underline-animated underline-button ${activeView === 'review' ? 'active' : ''}`}
            >
                Review
            </button> */}

            {/* <VersionDropdown /> */}
        </div>
    );
};

export default SubHeader;